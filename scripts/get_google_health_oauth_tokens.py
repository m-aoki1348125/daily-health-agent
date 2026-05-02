from __future__ import annotations

import argparse
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-untyped]

SCOPES = [
    "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
    "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
    "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly",
    "https://www.googleapis.com/auth/googlehealth.profile.readonly",
    "https://www.googleapis.com/auth/googlehealth.settings.readonly",
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Google Health OAuth locally and print tokens for Secret Manager."
    )
    parser.add_argument(
        "client_secret_json",
        type=Path,
        help="Path to downloaded OAuth client JSON.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Local callback port. Add http://127.0.0.1:PORT/ to the OAuth client.",
    )
    args = parser.parse_args()

    flow = InstalledAppFlow.from_client_secrets_file(
        str(args.client_secret_json),
        scopes=SCOPES,
    )
    credentials = flow.run_local_server(
        host="127.0.0.1",
        port=args.port,
        access_type="offline",
        prompt="consent",
    )

    print(f"GOOGLE_HEALTH_CLIENT_ID={credentials.client_id}")
    print(f"GOOGLE_HEALTH_CLIENT_SECRET={credentials.client_secret}")
    print(f"GOOGLE_HEALTH_REFRESH_TOKEN={credentials.refresh_token}")
    print(f"GOOGLE_HEALTH_GRANTED_SCOPES={' '.join(credentials.scopes or SCOPES)}")


if __name__ == "__main__":
    main()
