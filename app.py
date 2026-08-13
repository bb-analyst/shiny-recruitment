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
from modules.player_table import player_table_server, player_table_ui
from modules.rankings import rankings_server, rankings_ui

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
    player_table_ui("player_table", CONTRACT_END_CHOICES),
    leaderboards_ui("leaderboards"),
    rankings_ui("rankings"),
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
    fillable=True,
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
    def bigquery_data():
        reactive.invalidate_later(config.PLAYER_DATA_REFRESH_SECONDS)
        comps, seasons = selected_scope()

        df = queries.fetch_bq_player_data(client, comps, seasons, config.QUERY_STATS)
        return processing.calculate_rating(df)

    @reactive.calc
    def rankings_data():
        reactive.invalidate_later(config.PLAYER_DATA_REFRESH_SECONDS)
        comps, seasons = selected_scope()

        return queries.fetch_bq_rankings_data(client, comps, seasons)

    home_server("home", client)
    player_table_server("player_table", bigquery_data, contracts_df, credentials)
    leaderboards_server("leaderboards", bigquery_data)
    rankings_server("rankings", rankings_data)


app = App(app_ui, server, static_assets=config.APP_DIR / "www")
