from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone

from backend.core.config import settings


class AzureCognitiveTokenProvider:
    _token_cache: dict[str, tuple[str, datetime]] = {}

    @classmethod
    def get_bearer_token(cls) -> str:
        cached = cls._token_cache.get("cognitiveservices")
        now = datetime.now(timezone.utc)
        if cached and cached[1] > now + timedelta(minutes=5):
            return cached[0]

        result = subprocess.run(
            [
                settings.azure_cli_path,
                "account",
                "get-access-token",
                "--resource",
                "https://cognitiveservices.azure.com/",
                "--output",
                "json",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
        token = payload["accessToken"]
        expires_on_epoch = payload.get("expires_on")
        expires_on = payload.get("expiresOn")
        if expires_on_epoch:
            expires_at = datetime.fromtimestamp(int(expires_on_epoch), tz=timezone.utc)
        elif expires_on:
            parsed = datetime.fromisoformat(expires_on.replace("Z", "+00:00"))
            expires_at = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        else:
            expires_at = now + timedelta(minutes=50)
        cls._token_cache["cognitiveservices"] = (token, expires_at)
        return token
