"""BigQuery credentials and client construction."""

import os
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import bigquery
from google.oauth2 import service_account

PROJECT_ID = "rugbaleeg"
SERVICE_ACCOUNT_EMAIL = "shiny-recruitment@rugbaleeg.iam.gserviceaccount.com"

# Fallback for local development when the GCP_* variables are not set.
KEY_FILE = Path(__file__).parent.parent / "recruitment_bq.json"

_REQUIRED_ENV_VARS = [
    "GCP_PRIVATE_KEY_ID",
    "GCP_PRIVATE_KEY",
    "GCP_CLIENT_EMAIL",
    "GCP_CLIENT_ID",
]


def get_credentials() -> service_account.Credentials:
    """Build service account credentials from the environment.

    Falls back to recruitment_bq.json if the GCP_* variables are absent, and
    raises a message naming the missing variables if neither source works.
    """
    load_dotenv()

    missing = [name for name in _REQUIRED_ENV_VARS if not os.getenv(name)]

    if missing:
        if KEY_FILE.exists():
            return service_account.Credentials.from_service_account_file(str(KEY_FILE))
        raise RuntimeError(
            "Cannot authenticate to BigQuery. Missing environment variables: "
            f"{', '.join(missing)}. Set them in .env, or place a service account "
            f"key at {KEY_FILE}."
        )

    service_account_info = {
        "type": "service_account",
        "project_id": PROJECT_ID,
        "private_key_id": os.getenv("GCP_PRIVATE_KEY_ID"),
        # Env vars carry literal backslash-n; the key needs real newlines.
        "private_key": os.getenv("GCP_PRIVATE_KEY").replace("\\n", "\n"),
        "client_email": os.getenv("GCP_CLIENT_EMAIL"),
        "client_id": os.getenv("GCP_CLIENT_ID"),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": (
            "https://www.googleapis.com/robot/v1/metadata/x509/"
            f"{SERVICE_ACCOUNT_EMAIL.replace('@', '%40')}"
        ),
        "universe_domain": "googleapis.com",
    }

    return service_account.Credentials.from_service_account_info(service_account_info)


def get_bq_client(credentials: service_account.Credentials) -> bigquery.Client:
    return bigquery.Client(credentials=credentials)
