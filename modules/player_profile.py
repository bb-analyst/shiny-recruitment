"""Player profile page.

An opinionated analytical profile. The recruiter picks a player (and, when the
player has genuine exposure in more than one role, a role); everything else —
which metrics, which comparison pool, which neighbours — is fixed by the
methodology in ``profile_config.py`` and computed in ``data/profiles.py``.

The page answers four questions in order down the page:
  1. What type and level of player is this?      -> header + current profile
  2. How do they compare in their role?          -> percentile bars vs the pool
  3. Who has the most similar profile?            -> nearest neighbours
  4. Are they improving / declining / changing?   -> development trajectory
"""

import math

import pandas as pd
from shiny import module, reactive, render, req, ui

import config
import profile_config as pc
from data import profiles, queries

MAROON = "#540c2b"
GOLD = "#f0a91f"


# ---------------------------------------------------------------------------
# Presentation helpers
# ---------------------------------------------------------------------------

def _pct_color(pct):
    """Green (elite) -> amber -> red (poor) for a 0-100 percentile."""
    if pct is None or (isinstance(pct, float) and math.isnan(pct)):
        return "#c7ccd1"
    if pct >= 80: return "#1a9850"
    if pct >= 60: return "#66bd63"
    if pct >= 40: return "#fee08b"
    if pct >= 20: return "#fc8d59"
    return "#d73027"


def _fmt(value, decimals, unit=""):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    if decimals == 0:
        return f"{value:,.0f}{unit}"
    return f"{value:,.{decimals}f}{unit}"


def _ord(pct):
    """1-100 -> '1st', '2nd', ... for percentile labels."""
    if pct is None or (isinstance(pct, float) and math.isnan(pct)):
        return "—"
    n = int(round(pct))
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _recent_form(m):
    """Small recent-form fragment: 10-round value + directional arrow.

    Direction is judged on the raw value, oriented by whether higher is better
    for this metric, so an arrow always means "better" (up) or "worse" (down).
    """
    v10, v20, d = m["value10"], m["value20"], m["direction"]
    if v10 is None or v20 is None:
        return ui.span("Last 10: —", class_="pp-recent pp-flat")
    delta = (v10 - v20) * (1 if d >= 0 else -1)
    tol = 0.02 * (abs(v20) if v20 else 1)
    if delta > tol:
        arrow, cls = "▲", "pp-up"
    elif delta < -tol:
        arrow, cls = "▼", "pp-down"
    else:
        arrow, cls = "▬", "pp-flat"
    return ui.span(
        f"Last 10: {_fmt(v10, m['decimals'], m['unit'])} ",
        ui.span(arrow, class_=cls),
        class_="pp-recent",
    )


def _metric_row(m):
    """One readable metric row: label, value, percentile bar, recent form."""
    eligible = m["elig20"]
    pct = m["pct20"]
    if not eligible:
        bar = ui.div(
            ui.div(class_="pp-bar-fill", style="width:0%;background:#e6e6e6;"),
            ui.span("Insufficient sample", class_="pp-insufficient"),
            class_="pp-bar",
        )
        pct_label = ui.span("—", class_="pp-pct")
    else:
        color = _pct_color(pct)
        bar = ui.div(
            ui.div(class_="pp-bar-fill", style=f"width:{max(pct,1.5):.0f}%;background:{color};"),
            class_="pp-bar",
        )
        pct_label = ui.span(_ord(pct), class_="pp-pct", style=f"color:{color};")

    return ui.div(
        ui.div(
            ui.span(m["label"], class_="pp-metric-label"),
            ui.span(_fmt(m["value20"], m["decimals"], m["unit"]), class_="pp-value"),
            class_="pp-metric-head",
        ),
        bar,
        ui.div(pct_label, _recent_form(m), class_="pp-metric-foot"),
        class_="pp-metric-row",
    )


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

@module.ui
def player_profile_ui():
    return ui.nav_panel(
        "Player Profile",
        ui.div(
            ui.row(
                ui.column(
                    5,
                    ui.input_selectize(
                        "player", "Player",
                        choices={}, multiple=False, width="100%",
                        options={"placeholder": "Search for a player…"},
                    ),
                ),
                ui.column(7, ui.output_ui("role_selector")),
            ),
            class_="pp-controls",
        ),
        ui.output_ui("header"),
        ui.output_ui("no_profile"),
        ui.output_ui("body"),
    )


def _analytical_body():
    """The full analytical layout, shown only once a player qualifies."""
    return ui.TagList(
        ui.card(
            ui.card_header("Current profile — 20-round positional percentiles"),
            ui.output_ui("profile_metrics"),
        ),
        ui.card(
            ui.card_header("Most similar current players"),
            ui.output_ui("similar"),
            ui.div(
                "Selected player highlighted at top, then nearest profiles. "
                "Each cell shows the 20-round value with its positional percentile.",
                class_="pp-caption",
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

@module.server
def player_profile_server(input, output, session, client, comps, nav_request=None):
    """Profile page server.

    Everything the page shows — metric values, percentiles, pool sizes, nearest
    neighbours — is READ from the precomputed ``profile_derived`` table via
    ``client`` for the selected ``comps``. The page no longer fetches raw
    match-level rows.

    ``nav_request`` is a shared reactive.value set by other pages (e.g. the
    Player Table) to open a specific player here.
    """

    # Name of a requested player who has no qualifying profile, for messaging.
    nav_missing = reactive.value(None)

    @reactive.calc
    def derived_data():
        """Precomputed profile measures for the current competitions.

        Returns an empty frame (not an error) if the table has not been built
        yet, so the page can show a helpful message instead of crashing.
        """
        reactive.invalidate_later(config.PLAYER_DATA_REFRESH_SECONDS)
        try:
            return queries.fetch_bq_profile_data(client, comps())
        except Exception as exc:
            print(f"[player_profile] profile_derived read failed: {exc}")
            return pd.DataFrame()

    @reactive.calc
    def player_choices():
        idx = profiles.profile_player_index(derived_data())
        if idx.empty:
            return {}
        return {
            str(row["player_id"]): f"{row['player_name']} ({row['team']})"
            for _, row in idx.iterrows()
        }

    @reactive.effect
    def _populate_players():
        choices = player_choices()
        # Isolate the current selection so updating the control does not
        # re-trigger this effect (which would loop).
        with reactive.isolate():
            current = input.player()
        selected = current if current in choices else (next(iter(choices), None))
        ui.update_selectize("player", choices=choices, selected=selected)

    if nav_request is not None:
        @reactive.effect
        def _apply_nav_request():
            req_val = nav_request()
            if not req_val:
                return
            pid, name = req_val[0], req_val[1]
            key = str(pid)
            if key in player_choices():
                nav_missing.set(None)
                ui.update_selectize("player", selected=key)
            else:
                # Player exists but has no qualifying profile in this window.
                nav_missing.set(name)
                ui.update_selectize("player", selected="")

        @reactive.effect
        @reactive.event(input.player)
        def _clear_missing_on_manual_pick():
            if input.player() in player_choices():
                nav_missing.set(None)

    @reactive.calc
    def selectable_roles():
        pid = input.player()
        if not pid:
            return []
        d = derived_data()
        mine = d[(d["player_id"] == int(pid)) & (d["window_label"] == "20R")]
        if mine.empty:
            return []
        primary_comp = mine.groupby("competitionName")["pool_minutes"].max().idxmax()
        m = mine[mine["competitionName"] == primary_comp]
        order = m.groupby("role")["pool_minutes"].max().sort_values(ascending=False)
        return list(order.index)

    @render.ui
    def role_selector():
        roles = selectable_roles()
        if len(roles) <= 1:
            return ui.div(
                ui.tags.label("Role", class_="control-label"),
                ui.div(roles[0] if roles else "—", class_="pp-single-role"),
            ) if roles else None
        return ui.input_radio_buttons(
            "role", "Role", choices=roles, selected=roles[0], inline=True,
        )

    @reactive.calc
    def profile():
        d = derived_data()
        pid = input.player()
        req(pid)
        roles = selectable_roles()
        # input.role only exists when the radio is rendered (>1 role); reading a
        # not-yet-created input raises, so guard it.
        try:
            chosen = input.role()
        except Exception:
            chosen = None
        if chosen not in roles:
            chosen = None
        # No match-level frame: the development/match-log views were removed, so
        # temporal + match_log come back empty and nothing else needs them.
        return profiles.build_profile_from_table(d, None, int(pid), chosen)

    # ---- header + gating -------------------------------------------------

    @render.ui
    def header():
        p = profile()
        if p is None:
            return None
        win = _fmt_window(p.get("window"))
        chips = [
            _chip("Role", p["selected_role"]),
            _chip("Positional minutes", f"{p['pool_minutes']:,}"),
            _chip("Matches", str(p["pool_matches"])),
            _chip("Pool", str(p["pool_size"])),
        ]
        if win:
            chips.append(_chip("Window", win))
        if len(p["roles_available"]) > 1:
            others = ", ".join(
                f"{r['role']} ({r['minutes']}m)" for r in p["roles_available"][1:]
            )
            chips.append(_chip("Also seen", others))
        return ui.div(
            ui.div(
                ui.h2(p["player_name"], class_="pp-name"),
                ui.span(p["team"], class_="pp-team"),
                class_="pp-name-row",
            ),
            ui.div(*chips, class_="pp-chips"),
            class_="pp-header",
        )

    @render.ui
    def body():
        p = profile()
        if p is None:
            return None
        return _analytical_body()

    @render.ui
    def no_profile():
        # A player was opened from another page but has no qualifying profile.
        missing = nav_missing()
        if missing:
            return ui.div(
                ui.p(
                    f"{missing} has no qualifying profile in the current window — "
                    "they have not met the minimum positional minutes for any role. "
                    "Pick another player above.",
                    class_="pp-poolnote",
                ),
                class_="pp-empty",
            )
        # Shown when the precomputed table has no rows for the selected
        # competition (e.g. the precompute job has not been run for it).
        if not derived_data().empty:
            return None
        return ui.div(
            ui.p(
                "No precomputed profiles found for the selected competition. "
                "Run the profile precompute job to populate the profile_derived "
                "table for this competition.",
                class_="pp-poolnote",
            ),
            class_="pp-empty",
        )

    # ---- current profile -------------------------------------------------

    @render.ui
    def profile_metrics():
        p = profile()
        if p is None:
            return None
        return ui.div(*[_metric_row(m) for m in p["metrics"]], class_="pp-metrics")

    # ---- similar players (comparison table) ------------------------------

    @render.ui
    def similar():
        p = profile()
        if p is None:
            return None
        st = p.get("similar_table")
        if not st or len(st["rows"]) <= 1:
            return ui.p("No comparable players found in the current pool.",
                        class_="pp-caption")
        return _similar_table_ui(st)


def _similar_table_ui(st):
    """Comparison table: selected player (highlighted, top) + nearest profiles."""
    metrics = st["metrics"]
    header = ui.tags.tr(
        ui.tags.th("Player", class_="pp-st-player-h"),
        *[ui.tags.th(m["label"]) for m in metrics],
    )
    body = []
    for row in st["rows"]:
        tds = [ui.tags.td(
            ui.div(row["name"], class_="pp-st-name"),
            ui.div(row["team"], class_="pp-st-team"),
            class_="pp-st-player",
        )]
        for m in metrics:
            c = row["cells"][m["key"]]
            if not c["elig"] or c["value"] is None:
                tds.append(ui.tags.td(ui.span("—", class_="pp-st-na"),
                                      class_="pp-st-cell"))
            else:
                color = _pct_color(c["pct"])
                tds.append(ui.tags.td(
                    ui.div(_fmt(c["value"], m["decimals"], m["unit"]), class_="pp-st-val"),
                    ui.div(_ord(c["pct"]), class_="pp-st-pct"),
                    class_="pp-st-cell",
                    style=f"background:{color}22;box-shadow:inset 0 -2px 0 {color};",
                ))
        body.append(ui.tags.tr(*tds,
                               class_="pp-st-selected" if row["is_selected"] else ""))
    return ui.div(
        ui.tags.table(ui.tags.thead(header), ui.tags.tbody(*body), class_="pp-st-table"),
        class_="pp-st-wrap",
    )


def _fmt_window(w) -> str:
    """Format a window's round boundaries, e.g. '2026 R5–R24' or spanning
    seasons '2025 R23 – 2026 R1'."""
    if not w:
        return ""
    ss, sr, es, er = w["start_season"], w["start_round"], w["end_season"], w["end_round"]
    if ss == es:
        return f"{es} R{sr}–R{er}"
    return f"{ss} R{sr} – {es} R{er}"


def _chip(label, value):
    return ui.div(
        ui.span(label, class_="pp-chip-k"),
        ui.span(value, class_="pp-chip-v"),
        class_="pp-chip",
    )
