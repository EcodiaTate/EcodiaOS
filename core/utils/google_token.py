import asyncio
import json
import os
import time

import aiohttp
from dotenv import load_dotenv

load_dotenv(dotenv_path="D:/config/.env")
# Load .env variables

_GOOGLE_TOKEN = None
_GOOGLE_TOKEN_EXP = 0
_TOKEN_LOCK = asyncio.Lock()

GOOGLE_API_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


async def get_google_bearer_token():
    """
    Async singleton: returns a valid Google OAuth2 Bearer token for API calls.
    Automatically refreshes if expired.
    """
    global _GOOGLE_TOKEN, _GOOGLE_TOKEN_EXP

    async with _TOKEN_LOCK:
        now = int(time.time())
        if _GOOGLE_TOKEN and _GOOGLE_TOKEN_EXP - 60 > now:
            return _GOOGLE_TOKEN

        # --- Load key from file path ---
        keypath = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not keypath or not os.path.exists(keypath):
            raise RuntimeError("Missing or invalid GOOGLE_SERVICE_ACCOUNT_JSON path in .env")

        with open(keypath) as f:
            keydata = json.load(f)

        # --- Construct JWT manually ---
        import jwt  # PyJWT

        header = {"alg": "RS256", "typ": "JWT"}
        payload = {
            "iss": keydata["client_email"],
            "scope": " ".join(GOOGLE_API_SCOPES),
            "aud": "https://oauth2.googleapis.com/token",
            "iat": now,
            "exp": now + 3600,
        }
        private_key = keydata["private_key"]
        assertion = jwt.encode(payload, private_key, algorithm="RS256", headers=header)

        # --- Request access token ---
        token_url = "https://oauth2.googleapis.com/token"
        data = {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion}
        async with aiohttp.ClientSession() as session:
            async with session.post(token_url, data=data) as resp:
                resp.raise_for_status()
                resp_json = await resp.json()

        _GOOGLE_TOKEN = resp_json["access_token"]
        _GOOGLE_TOKEN_EXP = now + int(resp_json.get("expires_in", 3600))
        return _GOOGLE_TOKEN
