"""Broncos recruitment dashboard.

This file wires the app together: it builds the BigQuery client, defines the
data shared across pages, and mounts each page module. Page behaviour lives in
modules/, static configuration in config.py, and data access in data/.
"""

from shiny import App, reactive, req, ui
from shinyswatch import theme

import config
from data import client as bq_client
from data import processing, queries
from modules.home import home_server, home_ui
from modules.leaderboards import leaderboards_server, leaderboards_ui
from modules.player_profile import player_profile_server, player_profile_ui
from modules.player_table import player_table_server, player_table_ui

credentials = bq_client.get_credentials()
client = bq_client.get_bq_client(credentials)

# Contracts change rarely and are small; fetch once at startup.
contracts_df = queries.fetch_bq_contract_data(client)

# Players with no contract row first, then the expiry years actually present
# in the data.
CONTRACT_END_CHOICES = [config.UNSIGNED_LABEL] + [
    str(int(year)) for year in sorted(contracts_df["all_contract_end"].dropna().unique())
]


app_ui = ui.page_navbar(
    home_ui("home"),
    player_profile_ui("player_profile"),
    player_table_ui("player_table", CONTRACT_END_CHOICES),
    leaderboards_ui("leaderboards"),
    ui.nav_spacer(),
    ui.nav_control(
        ui.div(
            ui.input_selectize(
                "competition", None,
                choices={str(i): j for i, j in config.COMPS.items()},
                selected=config.DEFAULT_COMPS,
                multiple=True,
                width="200px",
            ),
        )
    ),
    ui.nav_control(
        ui.div(
            ui.input_selectize(
                "season", None,
                choices=[str(i) for i in config.SEASONS],
                selected=config.DEFAULT_SEASONS,
                multiple=True,
                width="200px",
            ),
        )
    ),
    title="Recruitment Dashboard",
    # Keep the grid/table pages filling the viewport, but let the long
    # Player Profile page flow and scroll normally instead of being clipped.
    fillable=["Home", "Player Table", "Leaderboards"],
    theme=theme.flatly(),
    id="navbar",
    header=ui.TagList(
        ui.tags.link(href="css.css", rel="stylesheet"),
        ui.tags.script(src="fixture-click.js"),
    ),
)


def server(input, output, session):
    """Shared data sources, plus one call per page module.

    The competition and season pickers live in the navbar, so the queries they
    drive are resolved here and handed to the pages that need them.
    """

    @reactive.calc
    def selected_scope():
        comps = [int(c) for c in input.competition()]
        seasons = [int(s) for s in input.season()]
        req(comps, seasons)
        return comps, seasons

    @reactive.calc
    def selected_comps():
        comps, _ = selected_scope()
        return comps

    # Cross-page navigation: a page sets this to request opening a player's
    # profile; the effect below switches to the Player Profile tab and the
    # profile module (which shares this value) selects the player.
    nav_request = reactive.value(None)

    @reactive.effect
    def _open_player_profile():
        if nav_request() is None:
            return
        ui.update_navs("navbar", selected="Player Profile")

    @reactive.calc
    def bigquery_data():
        reactive.invalidate_later(config.PLAYER_DATA_REFRESH_SECONDS)
        comps, seasons = selected_scope()

        df = queries.fetch_bq_player_data(client, comps, seasons, config.QUERY_STATS)
        return processing.calculate_rating(df)

    home_server("home", client)
    player_profile_server("player_profile", client, selected_comps, nav_request)
    player_table_server("player_table", bigquery_data, contracts_df, credentials, nav_request)
    leaderboards_server("leaderboards", bigquery_data)


app = App(app_ui, server, static_assets=config.APP_DIR / "www")
