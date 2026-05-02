from __future__ import annotations

import argparse
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

DEFAULT_SCOPES = ("sleep", "activity", "profile", "heartrate", "weight")
AUTHORIZE_URL = "https://www.fitbit.com/oauth2/authorize"
TOKEN_URL = "https://api.fitbit.com/oauth2/token"


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    server: OAuthCallbackServer

    def do_GET(self) -> None:  # noqa: N802
        query = parse_qs(urlparse(self.path).query)
        self.server.code = query.get("code", [None])[0]
        self.server.error = query.get("error", [None])[0]
        self.server.state = query.get("state", [None])[0]
        body = b"Fitbit OAuth completed. You can close this window."
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


class OAuthCallbackServer(HTTPServer):
    code: str | None = None
    error: str | None = None
    state: str | None = None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Fitbit OAuth locally and print tokens for Secret Manager."
    )
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--client-secret", required=True)
    parser.add_argument(
        "--scope",
        action="append",
        dest="scopes",
        default=[],
        help="Fitbit OAuth scope. Can be repeated. Defaults include weight.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()

    scopes = tuple(args.scopes or DEFAULT_SCOPES)
    state = secrets.token_urlsafe(24)
    server = OAuthCallbackServer((args.host, args.port), OAuthCallbackHandler)
    redirect_uri = f"http://{args.host}:{server.server_port}/callback"
    auth_url = f"{AUTHORIZE_URL}?{urlencode({
        'response_type': 'code',
        'client_id': args.client_id,
        'redirect_uri': redirect_uri,
        'scope': ' '.join(scopes),
        'expires_in': '31536000',
        'state': state,
    })}"

    print(f"Open this URL if the browser does not launch:\n{auth_url}\n")
    print(f"Fitbit app redirect URL must include: {redirect_uri}")
    webbrowser.open(auth_url)
    server.handle_request()

    if server.error:
        raise SystemExit(f"Fitbit OAuth failed: {server.error}")
    if not server.code or server.state != state:
        raise SystemExit("Fitbit OAuth failed: missing code or state mismatch")

    with httpx.Client(timeout=30) as client:
        response = client.post(
            TOKEN_URL,
            data={
                "client_id": args.client_id,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
                "code": server.code,
            },
            auth=(args.client_id, args.client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
    payload = response.json()

    print(f"FITBIT_CLIENT_ID={args.client_id}")
    print(f"FITBIT_CLIENT_SECRET={args.client_secret}")
    print(f"FITBIT_REFRESH_TOKEN={payload['refresh_token']}")
    print(f"FITBIT_GRANTED_SCOPE={payload.get('scope', ' '.join(scopes))}")


if __name__ == "__main__":
    main()
