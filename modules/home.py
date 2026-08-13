"""Home page: latest fixtures, with a click-through match summary modal."""

import html

import pandas as pd
from shiny import module, reactive, render, ui

import config
from data import queries


@module.ui
def home_ui():
    return ui.nav_panel(
        "Home",
        ui.h2("Welcome to the Recruitment Dashboard"),
        ui.p("Select a page from the navigation above. See the up to date data below."),
        ui.output_ui("fixture_cards"),
    )


@module.server
def home_server(input, output, session, client):
    # Resolved once so the delegated click handler in fixture-click.js knows
    # which namespaced input to set.
    fixture_input_id = session.ns("fixture_clicked")

    @reactive.calc
    def fixture_data():
        reactive.invalidate_later(config.FIXTURES_REFRESH_SECONDS)
        df = queries.fetch_bq_latest_fixtures(client)
        return df.sort_values(by=["competitionName", "roundId", "gameNumber"])

    @render.ui
    def fixture_cards():
        df = fixture_data()
        if df is None or len(df) == 0:
            return ui.p("No fixtures available.")

        grouped = df.groupby(["competitionId", "competitionName", "roundName"])

        cards = []
        for (comp_id, comp_name, round_name), group_df in grouped:
            rows = []
            for game in group_df.itertuples(index=False):
                state = "✅" if game.gameStateName == "Final" else "❌"
                rows.append(
                    f'<tr data-game-id="{html.escape(str(game.gameId))}">'
                    f"<td>{html.escape(str(game.gameNumber))}</td>"
                    f"<td>{html.escape(str(game.game))}</td>"
                    f"<td>{state}</td>"
                    f"</tr>"
                )
            table_html = (
                '<table class="table table-hover table-sm fixture-columns">'
                f'<tbody>{"".join(rows)}</tbody>'
                "</table>"
            )
            cards.append(
                ui.card(
                    ui.card_header(f"{comp_name} - {round_name}"),
                    ui.HTML(table_html),
                )
            )

        return ui.div(*cards, **{"data-fixture-input": fixture_input_id})

    # Match summaries are immutable once a game is final, so cache per session.
    game_summary_cache = {}

    def summary_modal(*body, title, size="m"):
        return ui.modal(
            *body,
            title=title,
            easy_close=True,
            size=size,
            footer=ui.modal_button("Close"),
        )

    @reactive.effect
    @reactive.event(input.fixture_clicked)
    def show_fixture_modal():
        clicked_id = input.fixture_clicked()
        fixtures = fixture_data()

        # Resolve the click against known fixtures so we only ever query a
        # gameId the app actually rendered.
        match = fixtures[fixtures["gameId"].astype(str) == str(clicked_id)]
        if match.empty:
            return
        fixture_row = match.iloc[0]

        # Match the parameter type to the column dtype rather than guessing
        # from the string the browser sent back.
        if pd.api.types.is_numeric_dtype(fixtures["gameId"]):
            game_id = int(fixture_row["gameId"])
        else:
            game_id = str(fixture_row["gameId"])

        title = (
            f"{fixture_row['game']} — "
            f"{fixture_row['competitionName']} {fixture_row['roundName']}"
        )

        cache_key = str(game_id)
        if cache_key not in game_summary_cache:
            try:
                game_summary_cache[cache_key] = queries.fetch_bq_game_summary(
                    client, game_id
                )
            except Exception as e:
                ui.modal_show(
                    summary_modal(
                        ui.p("Could not load the match summary."),
                        ui.pre(str(e)),
                        title=title,
                    )
                )
                return

        df = game_summary_cache[cache_key]

        if df is None or len(df) == 0:
            ui.modal_show(
                summary_modal(
                    ui.p("No player stats available for this match yet."),
                    title=title,
                )
            )
            return

        body = []
        for team_name, team_df in df.groupby("teamName", sort=False):
            team_df = team_df.drop(columns=["teamName"]).rename(columns=config.STATS_FLAT)
            body.append(ui.h5(team_name, style="margin-top: 12px;"))
            body.append(
                ui.HTML(
                    team_df.to_html(
                        index=False,
                        classes="table table-sm table-striped game-summary-table",
                        border=0,
                        na_rep="",
                    )
                )
            )

        ui.modal_show(summary_modal(*body, title=title, size="xl"))
