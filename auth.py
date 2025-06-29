# auth.py
import os
import time
import logging
import requests
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Token cache
_token_cache: Optional[dict] = None

# REST vs OAuth hosts
API_HOST   = os.getenv("API_HOST",   "api.usw2.pure.cloud")  # your default
OAUTH_HOST = os.getenv(
    "OAUTH_HOST",
    # if API_HOST starts with "api.", strip that and prefix "login."
    ("login." + API_HOST[len("api."):])
    if API_HOST.startswith("api.") else API_HOST
)

def get_token(force_refresh: bool = False) -> str:
    global _token_cache
    if not force_refresh and _token_cache:
        if time.time() < (_token_cache["expires_at"] - 300):
            return _token_cache["token"]

    client_id     = os.getenv("CLIENT_ID")
    client_secret = os.getenv("CLIENT_SECRET")
    if not all([client_id, client_secret]):
        raise ValueError("Missing CLIENT_ID or CLIENT_SECRET")

    logging.info("Fetching new access token from https://%s", OAUTH_HOST)
    resp = requests.post(
        f"https://{OAUTH_HOST}/oauth/token",
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials"},
        timeout=10,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    resp.raise_for_status()
    data = resp.json()

    token = data["access_token"]
    expires = data.get("expires_in", 3600)
    _token_cache = {
        "token":      token,
        "expires_at": time.time() + int(expires)
    }
    logging.info("Obtained token (expires in %ds)", expires)
    return token

def clear_token_cache():
    global _token_cache
    _token_cache = None
    logging.info("Token cache cleared")
