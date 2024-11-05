from loguru import logger
import requests, secrets
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from core.config import ALLOW_ANY_EMAIL
from shared.settings import get_settings
from db.database import get_db
from db import crud

settings = get_settings()
bearer_security = HTTPBearer()


def secure_compare(token, api_key):
    return secrets.compare_digest(token.encode("utf8"), api_key.encode("utf8"))


# Factory method to create an authentication dependency for a specific key
def api_key_auth(api_key):
    assert len(api_key) >= 20, "Invalid API key, must be at least 20 chars"

    async def auth(bearer: HTTPAuthorizationCredentials = Depends(bearer_security), auto_error=True):
        is_correct = secure_compare(bearer.credentials, api_key)
        if is_correct: return True

        if auto_error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Wrong auth credentials",
            )
        return False

    return auth


# --------------------- Token Auth for AA itself to query the API, AA setup tool and Prometheus
token_api_key_auth = api_key_auth(settings.API_BEARER_TOKEN)


async def get_token_or_user_auth(credentials: HTTPAuthorizationCredentials = Depends(bearer_security)):
    # tries to use the static API_KEY and defaults to google JWT auth
    if await token_api_key_auth(credentials, auto_error=False): return ALLOW_ANY_EMAIL
    return await get_user_auth(credentials)


async def get_user_auth(credentials: HTTPAuthorizationCredentials = Depends(bearer_security)):
    # validates the Bearer token in the case that it requires it
    valid_user, info = authenticate_user(credentials.credentials)
    if valid_user:
        return info
    logger.debug(f"TOKEN FAILURE: {valid_user=} {info=}")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=info,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_active_user_auth(credentials: HTTPAuthorizationCredentials = Depends(bearer_security)):
    # validates Bearer token and Active User status
    try: 
        email = await get_user_auth(credentials)
        with get_db() as db:
            if crud.is_active_user(db, email):
                return email
        raise HTTPException(status_code=403, detail="User is not active")
    except HTTPException as e:
        raise e


def authenticate_user(access_token):
    # https://cloud.google.com/docs/authentication/token-types#access
    if type(access_token) != str or len(access_token) < 10: return False, "invalid access_token"
    r = requests.get("https://oauth2.googleapis.com/tokeninfo", {"access_token": access_token})
    if r.status_code != 200: return False, "invalid token"
    try:
        j = r.json()
        if j.get("azp") not in settings.CHROME_APP_IDS and j.get("aud") not in settings.CHROME_APP_IDS:
            return False, f"token does not belong to valid APP_ID"
        if j.get("email") in settings.BLOCKED_EMAILS:
            return False, f"email '{j.get('email')}' not allowed"
        if j.get("email_verified") != "true":
            return False, f"email '{j.get('email')}' not verified"
        if int(j.get("expires_in", -1)) <= 0:
            return False, "Token expired"
        return True, j.get('email').lower()
    except Exception as e:
        logger.warning(f"AUTH EXCEPTION occurred: {e}")
        return False, "exception occurred"
