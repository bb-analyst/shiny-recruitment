"""Central configuration for the player profile page.

This module is the single source of truth for the profile methodology. The
profile is intentionally opinionated: once a player (and, where relevant, a
role) is chosen, everything else on the page is driven from the rules defined
here rather than from UI controls.

Nothing in this file is a UI concern. The processing pipeline in
``data/profiles.py`` reads these definitions and the UI in
``modules/player_profile.py`` renders whatever the pipeline produces. To change
the methodology — which metrics define a role, how many minutes qualify a
player, how many events a metric needs to be trustworthy, which representation
feeds similarity — edit this file and nothing else.

Open methodology decisions (see the brief) are deliberately expressed as
configuration here so they can be refined empirically later:

    1. Bench role classification      -> BENCH_CLASSIFIER / BENCH_HOOKER_DH80
    2. Metrics defining each role      -> ROLES[*]["metrics"]
    3. Minimum positional minutes      -> ROLES[*]["min_minutes"]
    4. Minimum event counts per metric -> METRICS[*]["min_events"]
    5. Percentile tie handling         -> PERCENTILE_METHOD
    6/7. Similarity + z vs robust-z    -> SIMILARITY
    8. Temporal smoothing              -> TEMPORAL
    9. Max calendar-age safeguard      -> MAX_WINDOW_AGE_ROUNDS
"""

# ---------------------------------------------------------------------------
# Analysis windows
# ---------------------------------------------------------------------------
# Windows are measured in *competition rounds*, not player appearances. A round
# is a distinct (seasonId, roundId) key in the data; finals continue the same
# sequence (roundId 28+ = Finals Week 1 .. Grand Final), so they belong to the
# window naturally rather than being excluded or treated as a new season.

CANONICAL_WINDOW = 20   # established current level ("the profile")
RECENT_WINDOW = 10      # recent-form signal
RECENT5_WINDOW = 5      # short-window signal (useful for shorter competitions)

# Optional safeguard so a very old observation cannot re-enter a "current"
# profile after a long absence. ``None`` disables it. When set, only rounds
# within this many rounds of the latest round can contribute, even if that
# leaves the player short of a full window. (Open decision #9 — off by default.)
MAX_WINDOW_AGE_ROUNDS = None

# ---------------------------------------------------------------------------
# Positional roles
# ---------------------------------------------------------------------------
# Analytical roles, not team-sheet positions. Starting players map directly from
# their listed position; bench (Interchange) players have their role *inferred*
# from how they are used (see BENCH_* below and data/profiles.py). Non-players
# (Reserve / Replacement / 0-minute rows) never enter a pool.

# Listed position (playerPosition) -> analytical role, for starters.
POSITION_TO_ROLE = {
    "Fullback":    "Fullback",
    "Winger":      "Wing",
    "Centre":      "Centre",
    "Five-Eighth": "Half",
    "Halfback":    "Half",
    "Hooker":      "Hooker",
    "2nd Row":     "Edge",
    "Prop":        "Middle",
    "Lock":        "Middle",
}

# Listed positions treated as bench (role inferred, not taken from the sheet).
BENCH_POSITIONS = ["Interchange"]

# Listed positions that mean the player did not meaningfully take the field.
NON_PLAYING_POSITIONS = ["Reserve", "Replacement", "18th Man"]

# Bench inference (open decision #1). Roles are assigned PER APPEARANCE (a bench
# player's role can vary game to game). Priority, when livexy signals are supplied:
#   1. Replacement: the role of the player they replaced at interchange (longest
#      stint), chained through interchanges. Carries ~93% of appearances.
#   2. Their modal starting role in the window (if they start elsewhere).
#   3. An event-signal cascade from that game's livexy positional data.
#   4. BENCH_FALLBACK_ROLE.
# When no livexy signals are supplied (e.g. the dashboard's live path), it falls
# back to the legacy heuristic: modal starting role, then a dummy-half fingerprint.
BENCH_CLASSIFIER = "replacement_then_modal_then_signal"
BENCH_HOOKER_DH80 = 4.0        # legacy fingerprint: dummy-half runs/80 => Hooker
BENCH_FALLBACK_ROLE = "Middle"  # forwards with no other signal default here

# Per-appearance event-signal cascade thresholds (tier 3). Rates are per 80 of
# that game's minutes; lat_off is the mean |Y - midfield| of the player's tackles.
BENCH_LATERAL_CENTER = 343.0    # lateral midfield in livexy Y units
BENCH_SIGNAL = dict(
    hooker_dh80=1.5,            # dummy-half runs/80 -> Hooker
    back_kick80=4.0,           # (kick returns + receipts)/80 -> back three ...
    back_max_tackles80=22,     #   ... only when tackle load is low (a back)
    fullback_max_lateral=195,  # fields kicks & central -> Fullback, else Wing
    half_pass80=20,            # passes/80 -> Half
    fwd_tackles80=33,          # forward pack: tackle- ...
    fwd_markers80=20,          #   ... or ruck-marker-heavy
    middle_markers80=34,       # Middle vs Edge: high markers ...
    middle_max_lateral=100,    #   ... and central defence -> Middle, else Edge
    wing_min_lateral=205,      # wide back, no kicks -> Wing, else Centre
)

# When the player subbed OFF held one of these (back) roles, the swap is rarely
# a like-for-like positional change — the backline reshuffles and the incoming
# bench player is usually a forward/utility. So for these, the incoming player's
# modal starting role is trusted AHEAD of the replacement role.
BENCH_NONPOSITIONAL_OFF = ["Fullback", "Wing", "Centre", "Half"]

# ---------------------------------------------------------------------------
# Metric catalogue
# ---------------------------------------------------------------------------
# Every metric the profile can display or feed into similarity. A metric value
# for a window is computed by summing the numerator and denominator columns
# across all of a player's qualifying rows in that window, then combining them —
# never by averaging per-match ratios — so players with different minutes are
# compared fairly.
#
# Fields:
#   label      display name.
#   num        column summed for the numerator.
#   den        column summed for the denominator, OR the sentinel "__mins80__"
#              meaning "rate per 80 minutes" (value = sum(num)/sum(mins)*80).
#   scale      multiply the ratio by this (100 turns a proportion into a %).
#   sample     column whose window sum is the metric's usable sample size.
#   min_events minimum sample before the metric is considered reliable. Below
#              this, the raw value may still be shown but NO percentile / minmax
#              / z-score / robust-z is calculated (insufficient sample).
#   direction  +1 if higher is better, -1 if lower is better. All normalised
#              measures are oriented so higher always means better regardless.
#   decimals   display precision for the raw value.
#   unit       optional suffix for display ("m", "%", "").
#   similarity whether the metric participates in the similarity model.
#
# Derived count columns referenced below (tackleAttempts, tryInvolvements,
# kicksFaced) are materialised in data/profiles.prepare_match_data.

METRICS = {
    "metresPerRun": dict(
        label="Metres / run", num="allRunMetres", den="allRuns", scale=1,
        sample="allRuns", min_events=20, direction=1, decimals=1, unit="m",
        similarity=True),
    "pcMetresPerRun": dict(
        label="Post-contact m/run", num="postContactMetres", den="allRuns", scale=1,
        sample="allRuns", min_events=20, direction=1, decimals=2, unit="m",
        similarity=True),
    "runMetres80": dict(
        label="Run metres / 80", num="allRunMetres", den="__mins80__", scale=1,
        sample="allRuns", min_events=20, direction=1, decimals=0, unit="m",
        similarity=True),
    "runsAtt": dict(
        label="Runs / 40 (att)", num="allRuns", den="__attackmin__", scale=1,
        sample="allRuns", min_events=20, direction=1, decimals=1, unit="",
        similarity=True),
    "tackleEff": dict(
        label="Tackle efficiency", num="tackles", den="tackleAttempts", scale=100,
        sample="tackleAttempts", min_events=40, direction=1, decimals=1, unit="%",
        similarity=True),
    "tackles80": dict(
        label="Tackles / 80", num="tackles", den="__mins80__", scale=1,
        sample="tackles", min_events=20, direction=1, decimals=1, unit="",
        similarity=True),
    "missedTackles80": dict(
        label="Missed tackles / 80", num="missedTackles", den="__mins80__", scale=1,
        sample="__mins__", min_events=1, direction=-1, decimals=1, unit="",
        similarity=True),
    "offloads80": dict(
        label="Offloads / 80", num="offloads", den="__mins80__", scale=1,
        sample="allRuns", min_events=20, direction=1, decimals=2, unit="",
        similarity=True),
    "tackleBreaks80": dict(
        label="Tackle breaks / 80", num="tackleBreaks", den="__mins80__", scale=1,
        sample="allRuns", min_events=20, direction=1, decimals=2, unit="",
        similarity=True),
    "linebreaks80": dict(
        label="Line breaks / 80", num="linebreaks", den="__mins80__", scale=1,
        sample="__mins__", min_events=1, direction=1, decimals=2, unit="",
        similarity=True),
    "tries80": dict(
        label="Tries / 80", num="tries", den="__mins80__", scale=1,
        sample="__mins__", min_events=1, direction=1, decimals=2, unit="",
        similarity=True),
    "tryInvolve80": dict(
        label="Try involvements / 80", num="tryInvolvements", den="__mins80__", scale=1,
        sample="__mins__", min_events=1, direction=1, decimals=2, unit="",
        similarity=True),
    "tryAssists80": dict(
        label="Try assists / 80", num="tryAssists", den="__mins80__", scale=1,
        sample="__mins__", min_events=1, direction=1, decimals=2, unit="",
        similarity=True),
    "lbAssists80": dict(
        label="Linebreak assists / 80", num="linebreakAssists", den="__mins80__", scale=1,
        sample="__mins__", min_events=1, direction=1, decimals=2, unit="",
        similarity=True),
    "kickMetres80": dict(
        label="Kick metres / 80", num="kickMetres", den="__mins80__", scale=1,
        sample="kicks", min_events=10, direction=1, decimals=0, unit="m",
        similarity=True),
    "forcedDO80": dict(
        label="Forced dropouts / 80", num="forcedDropOutKicker", den="__mins80__", scale=1,
        sample="kicks", min_events=10, direction=1, decimals=2, unit="",
        similarity=True),
    "dhRuns80": dict(
        label="Dummy-half runs / 80", num="dummyHalfRuns", den="__mins80__", scale=1,
        sample="__mins__", min_events=1, direction=1, decimals=1, unit="",
        similarity=True),
    "dhMetresPerRun": dict(
        label="Metres / dummy-half run", num="dummyHalfRunMetres", den="dummyHalfRuns", scale=1,
        sample="dummyHalfRuns", min_events=10, direction=1, decimals=1, unit="m",
        similarity=True),
    "krMetresPerReturn": dict(
        label="Metres / kick return", num="kickReturnMetres", den="kickReturns", scale=1,
        sample="kickReturns", min_events=10, direction=1, decimals=1, unit="m",
        similarity=True),
    "kickDefusalPct": dict(
        label="Kick defusal %", num="kicksDefused", den="kicksFaced", scale=100,
        sample="kicksFaced", min_events=10, direction=1, decimals=1, unit="%",
        similarity=True),
    "errorsAtt": dict(
        label="Errors / 40 (att)", num="errors", den="__attackmin__", scale=1,
        sample="__mins__", min_events=1, direction=-1, decimals=2, unit="",
        similarity=True),
    "tackleBreaksPerRun": dict(
        label="Tackle breaks / run", num="tackleBreaks", den="allRuns", scale=1,
        sample="allRuns", min_events=20, direction=1, decimals=2, unit="",
        similarity=True),
    "fastPtbPct": dict(
        label="Fast PTB %", num="ptbFast", den="ptbTotal", scale=100,
        sample="ptbTotal", min_events=40, direction=1, decimals=1, unit="%",
        similarity=True),
    "tackleAttemptsDef": dict(
        label="Tackle attempts / 40 (def)", num="tackleAttemptsAll", den="__defencemin__", scale=1,
        sample="tackleAttemptsAll", min_events=40, direction=1, decimals=1, unit="",
        similarity=True),
    "effTacklePct": dict(
        label="Effective tackle %", num="tackles", den="tackleAttemptsAll", scale=100,
        sample="tackleAttemptsAll", min_events=40, direction=1, decimals=1, unit="%",
        similarity=True),
    "penSixAgainsDef": dict(
        label="Pen + 6-agains / 40 (def)", num="disciplineConcessions", den="__defencemin__", scale=1,
        sample="__mins__", min_events=1, direction=-1, decimals=2, unit="",
        similarity=True),
    "lbInvolveAtt": dict(
        label="LB involvements / 40 (att)", num="lbInvolvements", den="__attackmin__", scale=1,
        sample="__mins__", min_events=1, direction=1, decimals=2, unit="",
        similarity=True),
    "tryInvolveAtt": dict(
        label="Try involvements / 40 (att)", num="tryInvolvementsAll", den="__attackmin__", scale=1,
        sample="__mins__", min_events=1, direction=1, decimals=2, unit="",
        similarity=True),
    "supportsAtt": dict(
        label="Supports / 40 (att)", num="supports", den="__attackmin__", scale=1,
        sample="__mins__", min_events=1, direction=1, decimals=1, unit="",
        similarity=True),
    "kickThreatsAtt": dict(
        label="Kick threats / 40 (att)", num="kickThreats", den="__attackmin__", scale=1,
        sample="__mins__", min_events=1, direction=1, decimals=2, unit="",
        similarity=True),
}

# ---------------------------------------------------------------------------
# Role definitions
# ---------------------------------------------------------------------------
# Each role fixes its ~5-7 defining metrics (the order here is the display and
# radar-axis order) and the minimum positional minutes a player must accumulate
# in a window to enter that role's comparison pool. Thresholds differ by role
# because bench and starting playing time differ, and differ by window because a
# 10-round window contains roughly half the exposure of a 20-round one — do not
# assume one value fits all (open decision #3; placeholders below).
#
#   min_minutes         -> gate for the canonical 20-round pool.
#   min_minutes_recent  -> gate for the 10-round recent-form pool.

ROLES = {
    # Outside backs share one set; Fullback and Wing add kick defusal % on top of
    # the Centre metrics.
    "Fullback": dict(
        min_minutes=400, min_minutes_recent=200,
        metrics=["runsAtt", "metresPerRun", "tackleBreaksPerRun", "fastPtbPct",
                 "lbInvolveAtt", "tryInvolveAtt", "kickDefusalPct",
                 "effTacklePct", "errorsAtt", "penSixAgainsDef"],
    ),
    "Wing": dict(
        min_minutes=400, min_minutes_recent=200,
        metrics=["runsAtt", "metresPerRun", "tackleBreaksPerRun", "fastPtbPct",
                 "lbInvolveAtt", "tryInvolveAtt", "kickDefusalPct",
                 "effTacklePct", "errorsAtt", "penSixAgainsDef"],
    ),
    "Centre": dict(
        min_minutes=400, min_minutes_recent=200,
        metrics=["runsAtt", "metresPerRun", "tackleBreaksPerRun", "fastPtbPct",
                 "lbInvolveAtt", "tryInvolveAtt", "effTacklePct",
                 "errorsAtt", "penSixAgainsDef"],
    ),
    "Half": dict(
        min_minutes=400, min_minutes_recent=200,
        metrics=["runsAtt", "supportsAtt", "lbInvolveAtt", "tryInvolveAtt",
                 "effTacklePct", "errorsAtt", "penSixAgainsDef", "kickThreatsAtt"],
    ),
    "Hooker": dict(
        min_minutes=250, min_minutes_recent=130,
        metrics=["runsAtt", "metresPerRun", "lbInvolveAtt",
                 "effTacklePct", "errorsAtt", "penSixAgainsDef"],
    ),
    # Edge and Middle share one forward-pack metric set (separate pools) so the
    # two roles are read on the same axes.
    "Edge": dict(
        min_minutes=350, min_minutes_recent=180,
        metrics=["runsAtt", "metresPerRun", "pcMetresPerRun",
                 "tackleBreaksPerRun", "fastPtbPct", "tackleAttemptsDef",
                 "effTacklePct", "errorsAtt", "penSixAgainsDef"],
    ),
    "Middle": dict(
        min_minutes=250, min_minutes_recent=130,
        metrics=["runsAtt", "metresPerRun", "pcMetresPerRun",
                 "tackleBreaksPerRun", "fastPtbPct", "tackleAttemptsDef",
                 "effTacklePct", "errorsAtt", "penSixAgainsDef"],
    ),
}

# Display order for the role selector and anywhere roles are listed.
ROLE_ORDER = ["Fullback", "Wing", "Centre", "Half", "Hooker", "Edge", "Middle"]

# Named analysis windows: label -> number of competition rounds.
WINDOWS = {"20R": CANONICAL_WINDOW, "10R": RECENT_WINDOW, "5R": RECENT5_WINDOW}


def min_minutes_for(role: str, window_len: int) -> int:
    """Positional-minute pool threshold for a role in a window of this length.

    The canonical length (>=20R) uses ``min_minutes``; the 10R window uses
    ``min_minutes_recent``; anything shorter (the 5R window) uses
    ``min_minutes_recent5`` if the role sets it, otherwise a pro-rata share of
    the recent threshold scaled by window length. Kept as a function so the rule
    lives in one place for both the dashboard and the precompute job.
    """
    cfg = ROLES[role]
    if window_len >= CANONICAL_WINDOW:
        return cfg["min_minutes"]
    if window_len >= RECENT_WINDOW:
        return cfg["min_minutes_recent"]
    return cfg.get(
        "min_minutes_recent5",
        round(cfg["min_minutes_recent"] * window_len / RECENT_WINDOW),
    )

# A player needs at least this many minutes in a *secondary* role before that
# role is offered in the selector (they always open on their primary role).
SECONDARY_ROLE_MIN_MINUTES = 200

# ---------------------------------------------------------------------------
# Normalisation + similarity methodology (open decisions #5, #6, #7)
# ---------------------------------------------------------------------------

# Percentile method / tie handling. Passed to pandas Series.rank(method=...).
# "average" gives tied players the mean of their ranks.
PERCENTILE_METHOD = "average"

# Robust spread floor: MAD is scaled to be a consistent SD estimator for normal
# data (x1.4826). If MAD is zero (>50% identical values) fall back to this
# fraction of the pool SD so robust-z stays finite.
MAD_SCALE = 1.4826

SIMILARITY = dict(
    # Which derived representation feeds the distance calc. One of:
    # "z_score", "robust_z", "percentile", "minmax". Retained precisely so this
    # can be swapped and evaluated without rebuilding the aggregation.
    representation="z_score",
    metric="euclidean",       # distance function over the representation
    n_neighbours=5,           # how many similar players to surface
    # A candidate must share at least this fraction of the role's similarity
    # metrics (both players eligible on the metric) to be comparable at all.
    min_shared_fraction=0.6,
)

# ---------------------------------------------------------------------------
# Temporal development (open decision #8)
# ---------------------------------------------------------------------------

TEMPORAL = dict(
    smoothing="rolling_mean",  # method for the smoothed player line
    window=5,                  # matches in the rolling window
    min_periods=2,             # minimum matches before a smoothed point is drawn
)
