import os
from pathlib import Path
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

if os.getenv("DJANGO_DEBUG", "True") == "True":
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

BASE_DIR = Path(__file__).resolve().parent.parent
CLIENT_SECRETS_FILE = BASE_DIR / "client_secrets.json"
TOKEN_FILE = BASE_DIR / "token.pickle"
SCOPES = ["https://www.googleapis.com/auth/drive"]


def load_credentials():
    if TOKEN_FILE.exists():
        with TOKEN_FILE.open("rb") as token:
            return pickle.load(token)
    return None


def save_credentials(creds):
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with TOKEN_FILE.open("wb") as token:
        pickle.dump(creds, token)


def create_oauth_flow(redirect_uri: str):
    return InstalledAppFlow.from_client_secrets_file(
        str(CLIENT_SECRETS_FILE),
        SCOPES,
        redirect_uri=redirect_uri,
    )


def authenticate_user():
    creds = load_credentials()

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_credentials(creds)
        return creds

    raise RuntimeError(
        "No valid Google Drive credentials found. Run the OAuth authorization flow first."
    )


if __name__ == "__main__":
    print("This helper is intended for the web OAuth flow. Use the /api/gdrive/auth-url/ endpoint.")
