from __future__ import annotations

import argparse
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Google Drive OAuth locally and print tokens for Secret Manager."
    )
    parser.add_argument(
        "client_secret_json",
        type=Path,
        help="Path to downloaded OAuth client JSON",
    )
    args = parser.parse_args()

    flow = InstalledAppFlow.from_client_secrets_file(
        str(args.client_secret_json),
        scopes=[DRIVE_SCOPE],
    )
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    print(f"DRIVE_OAUTH_CLIENT_ID={credentials.client_id}")
    print(f"DRIVE_OAUTH_CLIENT_SECRET={credentials.client_secret}")
    print(f"DRIVE_OAUTH_REFRESH_TOKEN={credentials.refresh_token}")


if __name__ == "__main__":
    main()
