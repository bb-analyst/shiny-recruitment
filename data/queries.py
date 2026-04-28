from google.cloud import bigquery
from google.oauth2 import service_account
import pandas as pd
from pathlib import Path

def get_client():
    key_path = Path(__file__).parent / "recruitment_bq.json"
    print(key_path)
    credentials = service_account.Credentials.from_service_account_file(str(key_path))
    return bigquery.Client(credentials=credentials)

def fetch_bq_player_data(
    client: bigquery.Client,
    comp: int,
    season: int,
    stats: list[str],
) -> pd.DataFrame:

    query = f"""
        SELECT {', '.join(stats)}
        FROM `rugbaleeg.statsperform.player-match-stats`
        WHERE competitionId = @comp
          AND seasonId = @season

    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("comp", "INT64", int(comp)),
            bigquery.ScalarQueryParameter("season", "INT64", int(season)),
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


def fetch_bq_rankings_data(client, comp_id, season):
    query = """
        SELECT 
            playerId, playerName, positionGroup,
            competitionId, competitionName, seasonId,
            gamesPlayed, totalMinutes,
            metric, raw_value, percentile_rank, zscore, minmax
        FROM `rugbaleeg.statsperform.season_derived_rankings`
        WHERE competitionId = @comp_id
          AND seasonId = @season
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("comp_id", "INT64", comp_id),
            bigquery.ScalarQueryParameter("season",  "INT64", season),
        ]
    )
    return client.query(query, job_config=job_config).to_dataframe()