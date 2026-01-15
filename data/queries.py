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
    WITH latest_rounds AS (
        SELECT 
            competitionId,
            MAX(roundStartDateUTC) as latest_round_date
        FROM `rugbaleeg.statsperform.fixtures`
        WHERE roundStartDateUTC <= CURRENT_TIMESTAMP()
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