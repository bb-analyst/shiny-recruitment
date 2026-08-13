"""Static configuration for the recruitment dashboard.

Everything here is constant for the life of the process: colours, competition
and season lists, the stat catalogue loaded from stats.json, and the per-page
defaults for leaderboards and rankings.
"""

import json
from pathlib import Path

APP_DIR = Path(__file__).parent

# -------------------------
# Branding
# -------------------------

BRONCOS_MAROON = "#540c2b"
BRONCOS_GOLD = "#f0a91f"

# Colours offered in the player-table highlight rule builder.
HIGHLIGHT_COLORS = {
    "#4ade80": "Green",
    "#facc15": "Amber",
    "#f87171": "Red",
}

# Name colouring in the player table by contract expiry year.
CONTRACT_END_COLORS = {
    2026: "#FF4444",  # red
    2027: "#E6970A",  # amber
}
UNSIGNED_COLOR = "#999999"

# Filter option for players with no contract row, whose contract end is NaN
# after the merge onto player stats.
UNSIGNED_LABEL = "Unsigned"

# -------------------------
# Competitions and seasons
# -------------------------

COMPS = {
    111: "nrl",
    113: "nswcup",
    114: "qcup",
    116: "origin",
    121: "superleague",
    143: "haroldmatthews",
    144: "sgball",
    153: "nrlq",
    154: "cyrilconnell",
    155: "malmeninga",
    159: "jerseyflegg",
    161: "nrlw",
}

SEASONS = [2023, 2024, 2025, 2026]

DEFAULT_COMPS = ["111"]
DEFAULT_SEASONS = ["2026"]

# -------------------------
# Stat catalogue
# -------------------------

with open(APP_DIR / "stats.json", "r") as f:
    STATS_DICT = json.load(f)

# {stat_key: short_display_name} across every category.
STATS_FLAT = {k: v for d in STATS_DICT.values() for k, v in d.items()}

# Categories offered in the stat pickers ("Always" is applied implicitly).
STAT_CATEGORIES = ["Derived", "Attack", "Defence", "Discipline", "Kicking"]

STAT_CHOICES = {category: STATS_DICT[category] for category in STAT_CATEGORIES}

# Every stat we pull from BigQuery. "Derived" columns are computed locally.
QUERY_STATS = [
    key
    for category in STATS_DICT
    if category != "Derived"
    for key in STATS_DICT[category]
]

DEFAULT_STATS = [
    "Rating", "allRuns", "allRunMetres",
    "tries", "tryAssists",
    "linebreaks", "linebreakAssists",
    "tackleBreaks",
    "tackles", "missedTackles", "ineffectiveTackles", "effectiveTacklePercentage",
    "errors", "penalties",
]

# -------------------------
# Player table
# -------------------------

SUMMARY_TYPES = ["Game Average", "Game Totals", "Per 80 Mins", "Individual Games"]

# Summary types whose thresholds scale with matches played.
TOTALS_SUMMARY_TYPES = ["Game Totals", "Season Totals"]

POSITIONS = [
    "Fullback", "Winger", "Centre", "Five-Eighth", "Halfback",
    "Hooker", "Prop", "2nd Row", "Lock", "Interchange",
]

# -------------------------
# Leaderboards
# -------------------------

LEADERBOARD_SUMMARY_TYPES = ["Game Average", "Game Totals", "Game Best"]

LEADERBOARD_DEFAULTS = {
    "WG": ["tries", "allRuns", "tackles"],
    "CT": ["tries", "allRuns", "tackles"],
    "FB": ["tries", "allRuns", "tackles"],
    "FE": ["tries", "allRuns", "tackles"],
    "HB": ["tries", "allRuns", "tackles"],
    "HK": ["tries", "allRuns", "tackles"],
    "2R": ["tries", "allRuns", "tackles"],
    "PR": ["tries", "allRuns", "tackles"],
    "LK": ["tries", "allRuns", "tackles"],
    "INT": ["tries", "allRuns", "tackles"],
}

# -------------------------
# Season rankings
# -------------------------

RANKING_POSITION_GROUPS = [
    "Halves", "Hookers", "Starting Middles",
    "Backrowers", "Outside Backs", "Bench",
]

RANKING_METHODS = {
    "percentile_rank": "Percentile Rank",
    "zscore": "Z-Score",
    "minmax": "Min-Max",
}

RANKING_DEFAULTS = {
    "Halves":           ["tries_per80", "tryAssists_per80", "linebreaks_per80", "kickMetres_per80", "errors_per80"],
    "Hookers":          ["tries_per80", "tackleBreaks_per80", "runs_per80", "tackles_per80", "errors_per80"],
    "Starting Middles": ["metres_per80", "runs_per80", "postContactMetres_per80", "tackleAttempts_per80", "errors_per80"],
    "Backrowers":       ["metres_per80", "tackleBreaks_per80", "offloads_per80", "tackleAttempts_per80", "errors_per80"],
    "Outside Backs":    ["tries_per80", "metres_per80", "tackleBreaks_per80", "kickDefusalPct", "errors_per80"],
    "Bench":            ["metres_per80", "runs_per80", "tackleAttempts_per80", "errors_per80", "sixAgains_per80"],
}

ALL_RANKING_METRICS = [
    "tries_per80", "tryAssists_per80", "linebreaks_per80", "linebreakAssists_per80",
    "tackleBreaks_per80", "runs_per80", "metres_per80", "postContactMetres_per80",
    "offloads_per80", "receipts_per80", "supports_per80", "halfbreaks_per80",
    "tackleAttempts_per80", "errors_per80", "penalties_per80", "sixAgains_per80",
    "tackleEfficiency", "ptbWinPct", "postContactMetresPct", "metresPerRun",
    "postContactMetresPerRun", "runsPerTackleBreak", "kickReturnMetresperkickReturn",
    "passesPerRun", "receiptsPerError", "kickDefusalPct", "fastPtbPct", "goalKickingPct",
]

# -------------------------
# Cache lifetimes (seconds)
# -------------------------

FIXTURES_REFRESH_SECONDS = 7200
PLAYER_DATA_REFRESH_SECONDS = 86400


def group_key(group: str) -> str:
    """Turn a ranking position group into a valid Shiny id fragment."""
    return group.replace(" ", "_")
