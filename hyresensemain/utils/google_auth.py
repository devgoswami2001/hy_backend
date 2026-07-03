from google.oauth2 import id_token
from google.auth.transport import requests
from django.conf import settings


def verify_google_token(token: str):
    try:
        payload = id_token.verify_oauth2_token(
            token,
            requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )

        # Extra safety checks
        if not payload.get("email_verified"):
            return None

        return {
            "email": payload.get("email"),
            "full_name": payload.get("name", ""),
            "first_name": payload.get("given_name", ""),
            "last_name": payload.get("family_name", ""),
        }

    except Exception:
        return None