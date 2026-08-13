"""Season rankings page: one tab per position group, normalised per 80 minutes."""

import pandas as pd
from shiny import module, render, ui

import config
from data import processing


@module.ui
def group_ui(group, default_metrics):
    """A single position-group tab: a metric picker and its ranking table."""
    return ui.nav_panel(
        group,
        ui.input_selectize(
            "metrics", "Metrics:",
            choices=config.ALL_RANKING_METRICS,
            selected=default_metrics,
            multiple=True,
            width="100%",
        ),
        ui.output_data_frame("table"),
    )


@module.server
def group_server(input, output, session, group, rankings_data, ranking_method):

    @render.data_frame
    def table():
        df = rankings_data()

        if df is None or len(df) == 0:
            return render.DataGrid(pd.DataFrame())

        final_df = processing.pivot_rankings_data(
            df,
            group,
            list(input.metrics()),
            ranking_method(),
        )

        return render.DataGrid(final_df, width="100%", filters=False, summary=False)


@module.ui
def rankings_ui():
    return ui.nav_panel(
        "Season Rankings",
        ui.layout_columns(
            ui.input_select(
                "ranking_method", "Ranking Method:",
                choices=config.RANKING_METHODS,
                selected="percentile_rank",
                width="150px",
            ),
            col_widths=[4],
            style="margin-bottom: 1rem;max-height: 50px;",
        ),
        ui.navset_tab(
            *[
                group_ui(config.group_key(group), group, config.RANKING_DEFAULTS[group])
                for group in config.RANKING_POSITION_GROUPS
            ]
        ),
    )


@module.server
def rankings_server(input, output, session, rankings_data):
    for group in config.RANKING_POSITION_GROUPS:
        group_server(
            config.group_key(group), group, rankings_data, input.ranking_method
        )
