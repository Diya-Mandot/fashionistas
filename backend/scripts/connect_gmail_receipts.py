"""Authorize the optional Gmail receipt importer with a read-only Desktop OAuth client."""

import argparse
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from google_auth_oauthlib.flow import InstalledAppFlow

from app.config import get_settings
from app.services.gmail_receipts import GMAIL_READONLY


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("client_file", type=Path, help="Google Desktop OAuth client JSON")
    args = parser.parse_args()
    target = Path(get_settings().gmail_receipts_token_file)
    if target.exists():
        parser.error(f"A Gmail token already exists at {target}. Remove it before connecting a different account.")
    flow = InstalledAppFlow.from_client_secrets_file(str(args.client_file), [GMAIL_READONLY])
    credentials = flow.run_local_server(host="127.0.0.1", port=0, prompt="consent")
    if not credentials.refresh_token:
        parser.error("Google did not grant offline access.")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with NamedTemporaryFile(mode="w", dir=target.parent, delete=False) as token:
        token.write(credentials.to_json())
    os.replace(token.name, target)
    print(f"Gmail authorized. Token saved to {target}.")


if __name__ == "__main__":
    main()
