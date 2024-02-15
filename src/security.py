from loguru import logger
import requests, os, re, secrets
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPBearer, HTTPAuthorizationCredentials


# Configuration
CHROME_APP_IDS = set([app_id.strip() for app_id in os.environ.get("CHROME_APP_IDS", "").split(",")])
assert len(CHROME_APP_IDS) > 0, "CHROME_APP_IDS env variable not properly set, it's a csv"
for app_id in CHROME_APP_IDS:
    assert len(app_id) > 10, f"CHROME_APP_IDS got invalid id: {app_id} env variable not set"
logger.info(f"{CHROME_APP_IDS=}")

BLOCKED_EMAILS = set([e.strip().lower() for e in os.environ.get("BLOCKED_EMAILS", "").split(",")])
logger.info(f"{len(BLOCKED_EMAILS)=}")

bearer_security = HTTPBearer()

ALLOW_ANY_EMAIL = "*"

def secure_compare(token, api_key):
    return secrets.compare_digest(token.encode("utf8"), api_key.encode("utf8"))

# Factory method to create an authentication dependency for a specific key
def api_key_auth(api_key):

    async def auth(bearer: HTTPAuthorizationCredentials = Depends(bearer_security), auto_error=True):
        assert len(api_key) >= 20, "Invalid API key, must be at least 20 chars"

        is_correct = secure_compare(bearer.credentials, api_key)
        if is_correct: return True

        if auto_error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Wrong auth credentials",
            )
        return False

    return auth

# --------------------- Static Auth for local AA deployments to add archives to the API
SFP = os.environ.get("STATIC_FILE_PASSWORD", "")  # min length is 20 chars
static_api_key_auth = api_key_auth(SFP)

# --------------------- Service Auth for the AA setup tool and Prometheus
SERVICE_PASSWORD = os.environ.get("SERVICE_PASSWORD", "")  # min length is 20 chars
service_api_key_auth = api_key_auth(SERVICE_PASSWORD)

# --------------------- Token Auth for AA itself to query the API
API_BEARER_TOKEN = os.environ.get("API_BEARER_TOKEN", "")  # min length is 20 chars
token_api_key_auth = api_key_auth(API_BEARER_TOKEN)

async def get_token_or_user_auth(credentials: HTTPAuthorizationCredentials = Depends(bearer_security)):
    # tries to use the static API_KEY and defaults to google JWT auth
    access_token = credentials.credentials
    if token_api_key_auth(access_token, auto_error=False): return ALLOW_ANY_EMAIL
    return await get_user_auth(credentials)

async def get_user_auth(credentials: HTTPAuthorizationCredentials = Depends(bearer_security)):
    # validates the Bearer token in the case that it requires it
    valid_user, info = authenticate_user(credentials.credentials)
    if valid_user: return info
    logger.debug(f"TOKEN FAILURE: {valid_user=} {info=}")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=info,
        headers={"WWW-Authenticate": "Bearer"},
    )

def authenticate_user(access_token):
    # https://cloud.google.com/docs/authentication/token-types#access
    if type(access_token) != str or len(access_token) < 10: return False, "invalid access_token"
    r = requests.get("https://oauth2.googleapis.com/tokeninfo", {"access_token": access_token})
    if r.status_code != 200: return False, "error occurred"
    try:
        j = r.json()
        if j.get("azp") not in CHROME_APP_IDS and j.get("aud") not in CHROME_APP_IDS:
            return False, f"token does not belong to valid APP_ID"
        if j.get("email") in BLOCKED_EMAILS:
            return False, f"email '{j.get('email')}' not allowed"
        if j.get("email_verified") != "true":
            return False, f"email '{j.get('email')}' not verified"
        if int(j.get("expires_in", -1)) <= 0:
            return False, "Token expired"
        return True, j.get('email')
    except Exception as e:
        logger.warning(f"EXCEPTION occurred: {e}")
        return False, f"EXCEPTION occurred"

