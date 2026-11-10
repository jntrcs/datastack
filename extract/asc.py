"""App Store Connect API auth. Python port of PersonalSite/worker/asc.js."""

import os
import time
from pathlib import Path

import jwt
import requests

API = "https://api.appstoreconnect.apple.com"


def token() -> str:
    """A 20-minute ES256 JWT, the longest Apple allows."""
    # Locally the key is a .p8 file; in GitHub Actions it's the secret's contents.
    key = os.environ.get("ASC_PRIVATE_KEY") or Path(os.environ["ASC_PRIVATE_KEY_PATH"]).expanduser().read_text()
    now = int(time.time())
    return jwt.encode(
        {"iss": os.environ["ASC_ISSUER_ID"], "iat": now, "exp": now + 1200, "aud": "appstoreconnect-v1"},
        key,
        algorithm="ES256",
        headers={"kid": os.environ["ASC_KEY_ID"], "typ": "JWT"},
    )


RETRYABLE = {429, 500, 502, 503, 504}


def get(tok: str, path: str, params: dict, accept: str = "application/json", attempts: int = 5) -> requests.Response:
    """GET with retries. Apple's API returns occasional transient 5xx/429s, so
    retry those with exponential backoff (2s, 4s, 8s, 16s) before giving up."""
    for attempt in range(attempts):
        res = requests.get(
            API + path,
            params=params,
            headers={"Authorization": f"Bearer {tok}", "Accept": accept},
            timeout=60,
        )
        if res.status_code not in RETRYABLE or attempt == attempts - 1:
            return res
        time.sleep(2 ** (attempt + 1))
    return res
