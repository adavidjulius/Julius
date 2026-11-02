#!/usr/bin/env python3
"""
Interactive Google Drive OAuth Authorizer for Julius.
Reads client credentials from credentials.json and generates a persistent token.json.
"""

import os
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]

def main():
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    creds_path = Path("credentials.json").resolve()
    token_path = Path("token.json").resolve()

    if not creds_path.exists():
        print(f"Error: {creds_path} not found. Please ensure credentials.json exists.")
        return

    print("Opening browser for Google Drive authorization...")
    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    creds = flow.run_local_server(port=8080)

    with open(token_path, "w") as f:
        f.write(creds.to_json())

    print(f"Successfully authenticated Google Drive! Token saved to: {token_path}")

if __name__ == "__main__":
    main()
