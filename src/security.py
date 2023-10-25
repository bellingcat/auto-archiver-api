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

basic_security = HTTPBasic()
bearer_security = HTTPBearer()

# --------------------- Bearer Auth
ALLOW_ANY_EMAIL = "*"


API_BEARER_TOKEN = os.environ.get("API_BEARER_TOKEN", "")  # min length is 20 chars
async def get_bearer_auth_token_or_jwt(credentials: HTTPAuthorizationCredentials = Depends(bearer_security)):
    # tries to use the static API_KEY and defaults to google JWT auth
    access_token = credentials.credentials
    if len(API_BEARER_TOKEN) >= 20: 
        current_token_bytes = access_token.encode("utf8")
        is_correct_token = secrets.compare_digest(current_token_bytes, API_BEARER_TOKEN.encode("utf8"))
        if is_correct_token: return ALLOW_ANY_EMAIL # any email works
    return await get_bearer_auth(credentials)

async def get_bearer_auth(credentials: HTTPAuthorizationCredentials = Depends(bearer_security)):
    # validates the Bearer token in the case that it requires it
    access_token = credentials.credentials
    valid_user, info = authenticate_user(access_token)
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


# --------------------- Basic Auth
SFP = os.environ.get("STATIC_FILE_PASSWORD", "")  # min length is 20 chars


async def get_basic_auth(credentials: HTTPBasicCredentials = Depends(basic_security)):
    # validates that the Basic token in the case that it requires it
    assert len(SFP) >= 20, "Invalid STATIC_FILE_PASSWORD, must be at least 20 chars"
    current_password_bytes = credentials.password.encode("utf8")
    is_correct_password = secrets.compare_digest(current_password_bytes, SFP.encode("utf8"))
    if is_correct_password: return True
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Wrong auth credentials",
        headers={"WWW-Authenticate": "Basic"}
    )

# --------------------- Server-side Auth
SERVICE_PASSWORD = os.environ.get("SERVICE_PASSWORD", "")  # min length is 20 chars


async def get_server_auth(credentials: HTTPBasicCredentials = Depends(basic_security)):
    # validates that the Basic token in the case that it requires it
    assert len(SERVICE_PASSWORD) >= 20, "Invalid SERVICE_PASSWORD, must be at least 20 chars"
    current_password_bytes = credentials.password.encode("utf8")
    is_correct_password = secrets.compare_digest(current_password_bytes, SERVICE_PASSWORD.encode("utf8"))
    if is_correct_password: return True
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Wrong auth credentials",
        headers={"WWW-Authenticate": "Basic"}
    )
