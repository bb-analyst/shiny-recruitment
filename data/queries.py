from google.cloud import bigquery
from google.oauth2 import service_account
import pandas as pd
from pathlib import Path
import json
from google.cloud import storage

def get_client():
    key_path = Path(__file__).parent / "recruitment_bq.json"
    print(key_path)
    credentials = service_account.Credentials.from_service_account_file(str(key_path))
    return bigquery.Client(credentials=credentials)

def fetch_bq_contract_data(
    client: bigquery.Client,
    current_year: int = 2026
) -> pd.DataFrame:
    
    query = f"""
        SELECT *
        FROM `rugbaleeg.statsperform.contracts`
        WHERE contract_year = {current_year}
    """

    return client.query(query).to_dataframe()

# Player stats now come from the derived livexy aggregate ``d_agg_player_match``
# (typed, one row per player-match) instead of the retired ``player-match-stats``
# table. That aggregate is keyed only by gameId/teamId/playerId, so the
# competition/season/round and team-name columns the app relies on are recovered
# by joining to ``fixtures`` on gameId. A few columns have no home in the new
# pipeline and are resolved here instead of read from the table.
PLAYER_MATCH_TABLE = "`rugbaleeg.statsperform.d_agg_player_match`"
FIXTURES_TABLE = "`rugbaleeg.statsperform.fixtures`"


def _team_side(col: str) -> str:
    """Pick the home/away variant of a team column based on the player's team."""
    return (
        f"CASE WHEN p.teamId = f.home_teamId "
        f"THEN f.home_{col} ELSE f.away_{col} END"
    )


# Requested columns that are not stored on d_agg_player_match: recovered from
# fixtures, computed, or blanked where the livexy pipeline no longer carries them.
_PLAYER_STAT_EXPR = {
    "competitionName": "f.competitionName",
    "seasonId": "f.seasonId",
    "roundId": "f.roundId",
    "roundName": "f.roundName",
    "teamName": _team_side("teamName"),
    "teamNickName": _team_side("teamNickName"),
    "teamAbbr": _team_side("teamAbbr"),
    # No source in the new pipeline — kept as blank columns for now.
    "teamHexColour": "CAST(NULL AS STRING)",
    "teamHexColour2": "CAST(NULL AS STRING)",
}


def _player_select(stats: list[str]) -> str:
    """Build the SELECT list, aliasing every column back to its stat key so the
    resulting DataFrame keeps the exact column names the app expects."""
    return ", ".join(
        f"{_PLAYER_STAT_EXPR.get(s, f'p.{s}')} AS `{s}`" for s in stats
    )


def fetch_bq_player_data(
    client: bigquery.Client,
    comps: list[int],
    seasons: list[int],
    stats: list[str],
) -> pd.DataFrame:

    query = f"""
        SELECT {_player_select(stats)}
        FROM {PLAYER_MATCH_TABLE} p
        JOIN {FIXTURES_TABLE} f ON p.gameId = f.gameId
        WHERE f.competitionId IN UNNEST(@comps)
          AND f.seasonId IN UNNEST(@seasons)
          AND p.playerId != 0
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("comps", "INT64", [int(c) for c in comps]),
            bigquery.ArrayQueryParameter("seasons", "INT64", [int(s) for s in seasons]),
        ]
    )

    job = client.query(query, job_config=job_config)
    job.result()

    return job.to_dataframe()


def fetch_bq_latest_fixtures(
    client: bigquery.Client
) -> pd.DataFrame:


    # Query to get all fixtures from the most recent past round of each competition
    query = """
    WITH round_first_game AS (
        SELECT
            competitionId,
            roundStartDateUTC,
            MIN(startTimeUTC) as first_game_time
        FROM `rugbaleeg.statsperform.fixtures`
        GROUP BY competitionId, roundStartDateUTC
    ),
    latest_rounds AS (
        SELECT
            competitionId,
            MAX(roundStartDateUTC) as latest_round_date
        FROM round_first_game
        WHERE first_game_time <= CURRENT_TIMESTAMP()
        GROUP BY competitionId
    )
    SELECT f.*
    FROM `rugbaleeg.statsperform.fixtures` f
    INNER JOIN latest_rounds lr
        ON f.competitionId = lr.competitionId
        AND f.roundStartDateUTC = lr.latest_round_date
    ORDER BY f.gameId
    """

    job = client.query(query)
    job.result()
    return job.to_dataframe()


GAME_SUMMARY_STATS = [
    'playerName', 'shirtNum', 'playerPositionAbbrev', 'teamName',
    'mins', 'allRuns', 'allRunMetres', 'postContactMetres',
    'tries', 'tryAssists', 'linebreaks', 'tackleBreaks', 'offloads',
    'tackles', 'missedTackles', 'errors'
]


def fetch_bq_game_summary(
    client: bigquery.Client,
    game_id
) -> pd.DataFrame:

    query = f"""
        SELECT {_player_select(GAME_SUMMARY_STATS)}
        FROM {PLAYER_MATCH_TABLE} p
        JOIN {FIXTURES_TABLE} f ON p.gameId = f.gameId
        WHERE p.gameId = @game_id
          AND p.playerId != 0
        ORDER BY `teamName`, `shirtNum`
    """

    param_type = "STRING" if isinstance(game_id, str) else "INT64"
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("game_id", param_type, game_id)
        ]
    )

    job = client.query(query, job_config=job_config)
    job.result()

    return job.to_dataframe()


def fetch_bq_rankings_data(client, comps, seasons):
    query = """
        SELECT 
            playerId, playerName, positionGroup,
            competitionId, competitionName, seasonId,
            gamesPlayed, totalMinutes,
            metric, raw_value, percentile_rank, zscore, minmax
        FROM `rugbaleeg.statsperform.season_derived_rankings`
        WHERE competitionId IN UNNEST(@comps)
          AND seasonId IN UNNEST(@seasons)
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("comps", "INT64", [int(c) for c in comps]),
            bigquery.ArrayQueryParameter("seasons", "INT64", [int(s) for s in seasons]),
        ]
    )
    return client.query(query, job_config=job_config).to_dataframe()



def fetch_bq_profile_data(client, comps):
    """Read precomputed profile measures from the profile_derived table.

    That table is produced by the separate ``profile-precompute`` project
    (github.com/bb-analyst/profile-precompute), scheduled outside this app.

    Returns the long derived table for the given competitions, all windows
    (20R + 10R), at each competition's **most recent** end-round. "Most recent"
    is by ``(end_seasonId, end_roundId)`` — season first — so a finals round
    (high roundId) in an older season can never outrank the current season.
    """
    query = """
        WITH latest AS (
            SELECT competitionId, end_seasonId, end_roundId
            FROM (
                SELECT competitionId, end_seasonId, end_roundId,
                       ROW_NUMBER() OVER (
                           PARTITION BY competitionId
                           ORDER BY end_seasonId DESC, end_roundId DESC
                       ) AS rn
                FROM (
                    SELECT DISTINCT competitionId, end_seasonId, end_roundId
                    FROM `rugbaleeg.statsperform.profile_derived`
                    WHERE competitionId IN UNNEST(@comps)
                )
            )
            WHERE rn = 1
        )
        SELECT d.*
        FROM `rugbaleeg.statsperform.profile_derived` d
        JOIN latest l
          ON d.competitionId = l.competitionId
         AND d.end_seasonId = l.end_seasonId
         AND d.end_roundId = l.end_roundId
    """
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ArrayQueryParameter("comps", "INT64", [int(c) for c in comps]),
    ])
    return client.query(query, job_config=job_config).to_dataframe()


def fetch_player_table_templates(credentials):
    client = storage.Client(credentials=credentials)
    bucket = client.bucket("rugbaleeg-bucket")
    blob = bucket.blob("shiny-recruitment/player_table_templates.json")
    if not blob.exists():
        return {}
    return json.loads(blob.download_as_text())

def save_player_table_templates(credentials, templates: dict):
    client = storage.Client(credentials=credentials)
    bucket = client.bucket("rugbaleeg-bucket")
    blob = bucket.blob("shiny-recruitment/player_table_templates.json")
    blob.upload_from_string(
        json.dumps(templates, indent=2),
        content_type="application/json"
    )