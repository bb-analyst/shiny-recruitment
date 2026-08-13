"""Leaderboards page: one tab per position, one card per selected stat."""

from shiny import module, render, ui

import config
from data import processing


@module.ui
def position_ui(position_abbrev, default_stats):
    """A single position tab: a stat picker and the grid cards it drives."""
    return ui.nav_panel(
        position_abbrev,
        ui.input_selectize(
            "stats", None,
            choices=config.STAT_CHOICES,
            selected=default_stats,
            multiple=True,
            width="100%",
        ),
        ui.output_ui("cards"),
    )


@module.server
def position_server(input, output, session, position_abbrev, bigquery_data, summary_inputs):
    """Render one leaderboard card per selected stat.

    The set of cards is reactive, so each card's grid output is registered on
    the fly as the cards are built. Re-registering an existing id simply
    replaces its renderer.
    """

    @render.ui
    def cards():
        stats = input.stats()
        if not stats:
            return ui.p("No stats selected.")

        summary_type = summary_inputs["summary"]()
        cards = []

        for stat in stats:
            output_id = f"grid_{stat}"
            stat_display_name = config.STATS_FLAT.get(stat, stat)

            cards.append(
                ui.div(
                    {"class": "col-12 col-sm-6 col-md-4 col-lg-3"},
                    ui.card(
                        ui.card_header(f"{stat_display_name} - {summary_type}"),
                        ui.output_data_frame(output_id),
                        class_="leaderboard-grid-card",
                    ),
                )
            )

            register_grid(stat, output_id)

        return ui.div({"class": "row"}, *cards)

    def register_grid(stat_name, output_id):
        @output(id=output_id)
        @render.data_frame
        def _():
            df = bigquery_data()
            df = df[df["playerPositionAbbrev"] == position_abbrev]

            leaderboard = processing.leaderboard_df(
                df,
                stat_name,
                summary_inputs["summary"](),
                summary_inputs["min_games"](),
                summary_inputs["top_n"](),
            )

            return render.DataGrid(
                leaderboard, width="100%", height="auto", filters=False, summary=False
            )

        return _


@module.ui
def leaderboards_ui():
    return ui.nav_panel(
        "Leaderboards",
        ui.layout_columns(
            ui.input_selectize(
                "summary", "Summary Type:",
                choices=config.LEADERBOARD_SUMMARY_TYPES,
                selected="Game Average",
            ),
            ui.input_slider("min_games", "Minimum Games:", value=5, min=1, max=10, step=1),
            ui.input_slider("top_n", "Top N Players:", value=5, min=1, max=10, step=1),
            col_widths=[4, 4, 4],
            style="margin-bottom: 1rem;max-height: 50px;",
        ),
        ui.navset_tab(
            *[
                position_ui(position, position, default_stats)
                for position, default_stats in config.LEADERBOARD_DEFAULTS.items()
            ]
        ),
    )


@module.server
def leaderboards_server(input, output, session, bigquery_data):
    # The three summary controls are shared by every position tab.
    summary_inputs = {
        "summary": input.summary,
        "min_games": input.min_games,
        "top_n": input.top_n,
    }

    for position in config.LEADERBOARD_DEFAULTS:
        position_server(position, position, bigquery_data, summary_inputs)
