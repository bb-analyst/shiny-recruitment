"""Player profile — dashboard (read) side.

Assembles the profile the page renders from measures that were **precomputed in
BigQuery** (the ``profile_derived`` table, built by the separate
``profile-precompute`` job). This module deliberately does NOT recompute
comparison pools; it reads them.

What it still computes locally is only the per-player, non-comparative views:
* the nearest-neighbour ranking, from the pool's stored standardised measures;
* the development time series and match log, from raw ``player-match-stats``
  rows (inherently per match).

All methodology/config lives in ``profile_config.py``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import profile_config as pc


# ---------------------------------------------------------------------------
# Match-level preparation (for the temporal charts + match log)
# ---------------------------------------------------------------------------

# Count columns derived once so metric definitions can reference real columns.
_DERIVED_COUNTS = {
    "tackleAttempts": ["tackles", "missedTackles"],
    "tackleAttemptsAll": ["tackles", "missedTackles", "ineffectiveTackles"],
    "tryInvolvements": ["tries", "tryAssists", "linebreakAssists"],
    # Try involvements = tries + assists + earlier-chain involvements.
    "tryInvolvementsAll": ["tries", "tryAssists", "tryInvolvement"],
    # Linebreak involvements = breaks made + assists + earlier-chain involvements.
    "lbInvolvements": ["linebreaks", "linebreakAssists", "linebreakInvolvement"],
    "kicksFaced": ["kicksDefused", "kicksNotDefused"],
    # Kick threats = forced dropouts + kick linebreaks + 40/20s + kick try
    # assists + long kicks that find space.
    "kickThreats": ["forcedDropOutKicker", "kickLineBreak", "fortyTwentyKicks",
                    "kickTryAssist", "longKicksSpace"],
    # Discipline concessions = penalties + both six-again types (ruck + 10m offside).
    "disciplineConcessions": [
        "penalties", "ruckInfringements", "setRestartConceded10mOffside"],
    # Play-the-balls completed in under three seconds (0-1s + 1-2s + 2-3s buckets).
    "ptbFast": ["ptbZeroToOne", "ptbOneToTwo", "ptbTwoToThree"],
}


def prepare_match_data(df: pd.DataFrame) -> pd.DataFrame:
    """Clean rows, derive helper counts, and assign an analytical role per row.

    Returns match-level rows (one per player-appearance) with added columns:
    ``role`` (analytical positional role), the derived count columns, and a
    global ``round_seq`` ordering competition rounds chronologically across
    the selected scope (finals included in sequence).
    """
    if df is None or len(df) == 0:
        return pd.DataFrame()

    df = df.copy()

    # Keep only genuine appearances. ``mins > 0`` drops Reserve/18th-man rows
    # regardless of how the position was labelled.
    if "mins" in df.columns:
        df = df[df["mins"].fillna(0) > 0]
    df = df[~df["playerPosition"].isin(pc.NON_PLAYING_POSITIONS)]
    if df.empty:
        return df

    # Derived count columns (safe against missing source columns).
    for out, parts in _DERIVED_COUNTS.items():
        present = [c for c in parts if c in df.columns]
        df[out] = df[present].fillna(0).sum(axis=1) if present else 0.0

    # Numeric hygiene for every column a metric might touch.
    metric_cols = set()
    for spec in pc.METRICS.values():
        for key in ("num", "den", "sample"):
            col = spec[key]
            if not col.startswith("__"):
                metric_cols.add(col)
    for col in metric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df = _assign_roles(df)
    df = _add_round_sequence(df)
    return df


def _assign_roles(df: pd.DataFrame) -> pd.DataFrame:
    """Assign each appearance an analytical role, inferring bench roles.

    Starters map straight from their listed position. Bench (Interchange) rows
    are resolved with the configured heuristic: inherit the player's most
    common starting role over the scope, else fall back to a stat fingerprint
    (dummy-half-heavy => Hooker, otherwise the fallback forward role).

    Kept in sync with the precompute job's copy so the reconstructed temporal
    window matches the pool the measures were computed in.
    """
    role = df["playerPosition"].map(pc.POSITION_TO_ROLE)

    is_bench = df["playerPosition"].isin(pc.BENCH_POSITIONS)

    # Each player's modal starting role, from the rows already mapped.
    starter_rows = df[role.notna()].assign(_role=role[role.notna()])
    modal_start = (
        starter_rows.groupby("playerId")["_role"]
        .agg(lambda s: s.value_counts().idxmax())
        if not starter_rows.empty else pd.Series(dtype=object)
    )

    # Fingerprint for players who only ever come off the bench: per-player
    # dummy-half runs per 80 across their bench minutes.
    bench = df[is_bench]
    if not bench.empty and "dummyHalfRuns" in bench.columns:
        agg = bench.groupby("playerId").agg(
            dh=("dummyHalfRuns", "sum"), mins=("mins", "sum"))
        dh80 = np.where(agg["mins"] > 0, agg["dh"] / agg["mins"] * 80, 0.0)
        fingerprint = pd.Series(
            np.where(dh80 >= pc.BENCH_HOOKER_DH80, "Hooker", pc.BENCH_FALLBACK_ROLE),
            index=agg.index,
        )
    else:
        fingerprint = pd.Series(dtype=object)

    def bench_role(pid):
        if pid in modal_start.index:
            return modal_start.loc[pid]
        if pid in fingerprint.index:
            return fingerprint.loc[pid]
        return pc.BENCH_FALLBACK_ROLE

    bench_roles = df.loc[is_bench, "playerId"].map(bench_role)
    role = role.copy()
    role.loc[is_bench] = bench_roles

    df = df.copy()
    df["role"] = role
    return df[df["role"].notna()]


def _add_round_sequence(df: pd.DataFrame) -> pd.DataFrame:
    """Order distinct competition rounds chronologically as an integer index."""
    keys = (
        df[["seasonId", "roundId"]]
        .drop_duplicates()
        .sort_values(["seasonId", "roundId"])
        .reset_index(drop=True)
    )
    keys["round_seq"] = np.arange(len(keys))
    return df.merge(keys, on=["seasonId", "roundId"], how="left")


def last_n_rounds(single_comp_df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Rows in the most recent ``n`` rounds of a single-competition frame.

    Sequences by ``(seasonId, roundId)`` alone, which is correct because the
    frame is already one competition. Used to reconstruct the exact window the
    precompute used, for the per-player temporal/match-log views.
    """
    if single_comp_df.empty:
        return single_comp_df
    ks = (single_comp_df[["seasonId", "roundId"]].drop_duplicates()
          .sort_values(["seasonId", "roundId"]).tail(n))
    return single_comp_df.merge(ks, on=["seasonId", "roundId"], how="inner")


# ---------------------------------------------------------------------------
# Similarity (over the pool's stored standardised measures)
# ---------------------------------------------------------------------------

def similarity_metrics(role: str, metric_keys: list | None = None) -> list:
    """The metrics used for similarity: the requested subset, or all eligible."""
    allowed = [k for k in pc.ROLES[role]["metrics"]
               if pc.METRICS[k].get("similarity", False)]
    if metric_keys:
        chosen = [k for k in allowed if k in set(metric_keys)]
        if chosen:
            return chosen
    return allowed


def _representation_matrix(long_df: pd.DataFrame, role: str,
                           representation: str | None = None,
                           metric_keys: list | None = None) -> tuple[pd.DataFrame, list]:
    """Player x similarity-metric matrix in the chosen representation."""
    metrics = similarity_metrics(role, metric_keys)
    rep = representation or pc.SIMILARITY["representation"]
    sub = long_df[long_df["metric"].isin(metrics)]
    mat = sub.pivot_table(index="player_id", columns="metric", values=rep, aggfunc="first")
    # Preserve configured metric order.
    mat = mat.reindex(columns=[m for m in metrics if m in mat.columns])
    return mat, metrics


def similar_players(long_df: pd.DataFrame, role: str, player_id, names: dict,
                    teams: dict, representation: str | None = None,
                    metric_keys: list | None = None) -> list[dict]:
    """Nearest statistical neighbours within the 20-round role pool."""
    mat, metrics = _representation_matrix(long_df, role, representation, metric_keys)
    if player_id not in mat.index or mat.shape[1] == 0:
        return []

    target = mat.loc[player_id]
    need = max(1, int(np.ceil(pc.SIMILARITY["min_shared_fraction"] * len(metrics))))

    results = []
    for pid, row in mat.iterrows():
        if pid == player_id:
            continue
        shared = target.notna() & row.notna()
        n_shared = int(shared.sum())
        if n_shared < need:
            continue
        diff = (target[shared] - row[shared]).astype(float)
        dist = float(np.sqrt(np.sum(diff ** 2)) / np.sqrt(n_shared))  # RMS distance

        per_metric = diff.abs().sort_values()
        top_similar = [pc.METRICS[m]["label"] for m in per_metric.index[:2]]
        top_diff = [pc.METRICS[m]["label"] for m in per_metric.index[::-1][:2]]

        results.append({
            "player_id": pid,
            "name": names.get(pid, str(pid)),
            "team": teams.get(pid, ""),
            "distance": dist,
            "top_similar": top_similar,
            "top_diff": top_diff,
        })

    results.sort(key=lambda r: r["distance"])
    return results[: pc.SIMILARITY["n_neighbours"]]


# ---------------------------------------------------------------------------
# Temporal development
# ---------------------------------------------------------------------------

def temporal_series(window_df: pd.DataFrame, role: str, player_id,
                    pool_long: pd.DataFrame) -> dict:
    """Match-level series + smoothed line + pool-percentile view per metric.

    For each defining metric returns the player's per-match raw value (ordered
    chronologically), a rolling-average smoothed line, and the same values
    expressed as a percentile against the current 20-round pool distribution so
    the UI can toggle between raw units and positional percentile.
    """
    rows = window_df[(window_df["role"] == role) &
                     (window_df["playerId"] == player_id)].sort_values("round_seq")
    out = {}
    if rows.empty:
        return out

    win = pc.TEMPORAL["window"]
    minp = pc.TEMPORAL["min_periods"]

    for key in pc.ROLES[role]["metrics"]:
        spec = pc.METRICS[key]
        num = rows[spec["num"]] if spec["num"] in rows else pd.Series(0.0, index=rows.index)
        if spec["den"] == "__mins80__":
            val = np.where(rows["mins"] > 0, num / rows["mins"] * 80 * spec["scale"], np.nan)
        elif spec["den"] in ("__attackmin__", "__defencemin__"):
            col = "attackMins" if spec["den"] == "__attackmin__" else "defenceMins"
            phase = rows[col] if col in rows else pd.Series(np.nan, index=rows.index)
            val = np.where(phase > 0, num / phase * 40 * spec["scale"], np.nan)
        else:
            den = rows[spec["den"]] if spec["den"] in rows else pd.Series(0.0, index=rows.index)
            val = np.where(den > 0, num / den * spec["scale"], np.nan)
        series = pd.Series(val, index=rows.index).astype(float)
        smooth = series.rolling(win, min_periods=minp).mean()

        # Pool distribution for this metric (eligible players' 20R values).
        pool_vals = pool_long[(pool_long["metric"] == key) & pool_long["eligible"]]["metric_value"]
        pct = [_value_to_percentile(v, pool_vals, spec["direction"]) for v in series]
        pct_smooth = [_value_to_percentile(v, pool_vals, spec["direction"]) for v in smooth]

        out[key] = {
            "label": spec["label"],
            "unit": spec["unit"],
            "round": rows["roundName"].tolist(),
            "seq": rows["round_seq"].tolist(),
            "value": [None if pd.isna(v) else float(v) for v in series],
            "smooth": [None if pd.isna(v) else float(v) for v in smooth],
            "percentile": [None if p is None else float(p) for p in pct],
            "percentile_smooth": [None if p is None else float(p) for p in pct_smooth],
        }
    return out


def _value_to_percentile(value, pool_vals: pd.Series, direction: int):
    """Where a single value would rank (0-100) in the pool, oriented."""
    if value is None or pd.isna(value) or len(pool_vals) < 2:
        return None
    better = (pool_vals <= value) if direction >= 0 else (pool_vals >= value)
    return float(better.mean() * 100)


# ---------------------------------------------------------------------------
# Table-backed profile (dashboard reads precomputed measures from BigQuery)
# ---------------------------------------------------------------------------

def build_profile_from_table(derived: pd.DataFrame, match_df: pd.DataFrame,
                             player_id, role: str | None = None) -> dict | None:
    """Assemble the profile payload from precomputed measures.

    ``derived`` is the long ``profile_derived`` slice for the current scope (both
    windows, one end-round per competition). The comparison-heavy parts —
    metric values, percentiles, pool size, nearest neighbours — come straight
    from that table so they match the batch exactly. The per-player temporal
    charts and match log are still derived from ``match_df`` (prepared
    match-level rows), because they are single-player views, not pool
    comparisons.

    Returns None if the player has no precomputed profile (i.e. did not qualify
    for any pool in scope).
    """
    if derived is None or derived.empty:
        return None
    mine = derived[derived["player_id"] == player_id]
    if mine.empty:
        return None

    # A player can qualify in more than one competition; open the profile on the
    # competition where they have the most positional minutes.
    twenty = mine[mine["window_label"] == "20R"]
    if twenty.empty:
        return None
    primary_comp = (
        twenty.groupby("competitionName")["pool_minutes"].max().idxmax()
    )
    dcomp = derived[derived["competitionName"] == primary_comp]
    d20 = dcomp[dcomp["window_label"] == "20R"]
    d10 = dcomp[dcomp["window_label"] == "10R"]
    mine20 = d20[d20["player_id"] == player_id]

    # Roles the player qualifies for (present in the pool), most minutes first.
    role_minutes = (mine20.groupby("role")["pool_minutes"].max()
                    .sort_values(ascending=False))
    role_matches = mine20.groupby("role")["matches"].max()
    roles_available = [
        {"role": r, "minutes": int(role_minutes[r]), "matches": int(role_matches[r])}
        for r in role_minutes.index
    ]
    primary_role = roles_available[0]["role"]
    selectable = [r["role"] for r in roles_available]
    selected_role = role if role in selectable else primary_role

    r20 = d20[(d20["player_id"] == player_id) & (d20["role"] == selected_role)]
    r10 = d10[(d10["player_id"] == player_id) & (d10["role"] == selected_role)]
    by_metric_20 = {row["metric"]: row for _, row in r20.iterrows()}
    by_metric_10 = {row["metric"]: row for _, row in r10.iterrows()}

    metrics_payload = []
    for key in pc.ROLES[selected_role]["metrics"]:
        spec = pc.METRICS[key]
        a = by_metric_20.get(key)
        b = by_metric_10.get(key)
        metrics_payload.append({
            "key": key, "label": spec["label"], "unit": spec["unit"],
            "decimals": spec["decimals"], "direction": spec["direction"],
            "value20": None if a is None else _num(a["metric_value"]),
            "pct20": None if (a is None or not a["eligible"]) else _num(a["percentile"]),
            "elig20": bool(a is not None and a["eligible"]),
            "sample20": None if a is None else _num(a["sample"]),
            "value10": None if b is None else _num(b["metric_value"]),
            "pct10": None if (b is None or not b["eligible"]) else _num(b["percentile"]),
            "elig10": bool(b is not None and b["eligible"]),
        })

    head = r20.iloc[0] if not r20.empty else mine20.iloc[0]
    pool_minutes = int(head["pool_minutes"])
    pool_matches = int(head["matches"])
    pool_size = int(head["pool_size"])
    pool_size_recent = int(r10.iloc[0]["pool_size"]) if not r10.empty else 0

    # Exact round boundaries of each window, so the UI can label which window
    # this profile represents.
    window = _window_bounds(head, pc.CANONICAL_WINDOW)
    window_recent = _window_bounds(r10.iloc[0], pc.RECENT_WINDOW) if not r10.empty else None

    # This role's pool (used for the temporal pool-percentile view). The
    # nearest-neighbour computation is done separately via compute_similarity so
    # the UI can vary the representation and metric subset interactively.
    pool20 = d20[d20["role"] == selected_role]

    # Temporal + match log from the reconstructed window of match-level rows.
    temporal, match_log = {}, pd.DataFrame()
    if match_df is not None and not match_df.empty:
        comp_match = match_df[match_df["competitionName"] == primary_comp]
        window_df = last_n_rounds(comp_match, pc.CANONICAL_WINDOW)
        if not window_df.empty:
            if "round_seq" not in window_df.columns:
                window_df = _add_round_sequence(window_df)
            temporal = temporal_series(window_df, selected_role, player_id, pool20)
            match_log = _match_log(window_df, selected_role, player_id)

    return {
        "player_id": int(player_id),
        "player_name": str(head["player_name"]),
        "team": str(head["team"]),
        "roles_available": roles_available,
        "selectable_roles": selectable,
        "primary_role": primary_role,
        "selected_role": selected_role,
        "competition": primary_comp,
        "min_minutes": pc.min_minutes_for(selected_role, pc.CANONICAL_WINDOW),
        "pool_minutes": pool_minutes,
        "pool_matches": pool_matches,
        "pool_eligible": True,  # only qualifying players appear in the table
        "pool_size": pool_size,
        "pool_size_recent": pool_size_recent,
        "window": window,
        "window_recent": window_recent,
        "metrics": metrics_payload,
        "temporal": temporal,
        "match_log": match_log,
    }


def compute_similarity(derived: pd.DataFrame, competition: str, role: str,
                       player_id, representation: str | None = None,
                       metric_keys: list | None = None) -> dict:
    """Nearest neighbours + comparison table for a role pool, on demand.

    ``representation`` picks which stored measure feeds the distance
    ("z_score" / "robust_z" / "percentile" / "minmax"); ``metric_keys`` limits
    similarity to a subset of the role's metrics. Both default to the config
    (all similarity metrics, SIMILARITY["representation"]) when None.
    """
    empty = {"similar": [], "similar_table": None}
    if derived is None or derived.empty:
        return empty
    pool = derived[(derived["window_label"] == "20R")
                   & (derived["competitionName"] == competition)
                   & (derived["role"] == role)]
    if pool.empty:
        return empty
    names = dict(zip(pool["player_id"], pool["player_name"]))
    teams = dict(zip(pool["player_id"], pool["team"]))
    similar = similar_players(pool, role, player_id, names, teams,
                              representation=representation, metric_keys=metric_keys)
    table = similarity_table(pool, role, player_id,
                             [s["player_id"] for s in similar], names, teams,
                             metric_keys=metric_keys)
    return {"similar": similar, "similar_table": table}


def _window_bounds(row, n_rounds: int) -> dict:
    """Extract a window's round boundaries from a profile_derived row."""
    return {
        "start_season": int(row["start_seasonId"]),
        "start_round": int(row["start_roundId"]),
        "end_season": int(row["end_seasonId"]),
        "end_round": int(row["end_roundId"]),
        "n_rounds": int(row["n_rounds_present"]),
        "target_rounds": n_rounds,
    }


def similarity_table(pool20: pd.DataFrame, role: str, selected_id,
                     neighbour_ids: list, names: dict, teams: dict,
                     metric_keys: list | None = None) -> dict:
    """Side-by-side metric table for the selected player + nearest neighbours.

    The selected player is first (and flagged), then neighbours in similarity
    order. Each cell carries the raw value, its positional percentile and
    whether the player met the metric's sample threshold, so the UI can show
    the actual numbers rather than only a ranked list.

    All of the role's defining metrics are shown as columns for full context;
    ``metric_keys`` marks which ones fed the similarity calculation (via each
    column's ``in_calc`` flag) so the UI can highlight those headers.
    """
    metrics = pc.ROLES[role]["metrics"]
    in_calc = set(similarity_metrics(role, metric_keys))
    lut = {(r.player_id, r.metric): r for r in pool20.itertuples()}

    def row_for(pid, is_selected):
        cells = {}
        for key in metrics:
            r = lut.get((pid, key))
            if r is None:
                cells[key] = {"value": None, "pct": None, "elig": False}
            else:
                elig = bool(r.eligible)
                cells[key] = {
                    "value": _num(r.metric_value),
                    "pct": _num(r.percentile) if elig else None,
                    "elig": elig,
                }
        return {
            "player_id": int(pid),
            "name": names.get(pid, str(pid)),
            "team": teams.get(pid, ""),
            "is_selected": is_selected,
            "cells": cells,
        }

    rows = [row_for(selected_id, True)] + [row_for(pid, False) for pid in neighbour_ids]
    metric_defs = [
        {"key": k, "label": pc.METRICS[k]["label"], "unit": pc.METRICS[k]["unit"],
         "decimals": pc.METRICS[k]["decimals"], "in_calc": k in in_calc}
        for k in metrics
    ]
    return {"metrics": metric_defs, "rows": rows}


def profile_player_index(derived: pd.DataFrame) -> pd.DataFrame:
    """Distinct players that have a precomputed profile, for the selector.

    One row per player (their primary competition + team), so only players with
    a qualifying profile can be chosen.
    """
    if derived is None or derived.empty:
        return pd.DataFrame(columns=["player_id", "player_name", "team", "competitionName"])
    twenty = derived[derived["window_label"] == "20R"]
    # Primary competition = most pool minutes.
    idx = (twenty.sort_values("pool_minutes", ascending=False)
           .drop_duplicates("player_id")[
               ["player_id", "player_name", "team", "competitionName"]]
           .sort_values("player_name")
           .reset_index(drop=True))
    return idx


def _match_log(window_df, role, player_id) -> pd.DataFrame:
    """Per-match contributions behind the profile, most recent first."""
    cols = ["roundName", "teamAbbr", "playerPositionAbbrev", "mins",
            "allRuns", "allRunMetres", "tackleBreaks", "tries", "tryAssists",
            "tackles", "missedTackles", "errors"]
    rows = window_df[(window_df["role"] == role) &
                     (window_df["playerId"] == player_id)]
    present = [c for c in cols if c in rows.columns]
    return rows.sort_values("round_seq", ascending=False)[present].reset_index(drop=True)


def _num(x):
    if x is None or (isinstance(x, float) and np.isnan(x)) or pd.isna(x):
        return None
    return float(x)
