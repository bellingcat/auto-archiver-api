from loguru import logger
import requests, os, re, secrets
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPBearer, HTTPAuthorizationCredentials



# Configuration
GOOGLE_CHROME_APP_ID = os.environ.get("GOOGLE_CHROME_APP_ID")
assert len(GOOGLE_CHROME_APP_ID)>10, "GOOGLE_CHROME_APP_ID env variable not set"
GOOGLE_CHROME_APP_ID_PUBLIC = os.environ.get("GOOGLE_CHROME_APP_ID_PUBLIC")
assert len(GOOGLE_CHROME_APP_ID_PUBLIC)>10, "GOOGLE_CHROME_APP_ID_PUBLIC env variable not set"
logger.info(f"{GOOGLE_CHROME_APP_ID_PUBLIC=}")
ALLOWED_EMAILS = set([e.strip().lower() for e in os.environ.get("ALLOWED_EMAILS", "").split(",")])
assert len(ALLOWED_EMAILS)>=1, "at least one ALLOWED_EMAILS is required from the env variable"
logger.info(f"{len(ALLOWED_EMAILS)=}")

basic_security = HTTPBasic()
bearer_security = HTTPBearer()

#--------------------- Bearer Auth

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
    if type(access_token)!=str or len(access_token)<10: return False, "invalid access_token"
    r = requests.get("https://oauth2.googleapis.com/tokeninfo", {"access_token":access_token})
    if r.status_code!=200: return False, "error occurred"
    try:
        j = r.json()
        if j.get("azp") != GOOGLE_CHROME_APP_ID and j.get("aud")!=GOOGLE_CHROME_APP_ID: 
            return False, f"token does not belong to correct APP_ID"
        # if j.get("email") not in ALLOWED_EMAILS: 
        if not custom_is_email_allowed(j.get("email"), any_bellingcat_email=True):
            return False, f"email '{j.get('email')}' not allowed"
        if j.get("email_verified") != "true": 
            return False, f"email '{j.get('email')}' not verified"
        if int(j.get("expires_in", -1)) <= 0:
            return False, "Token expired"
        return True, j.get('email')
    except Exception as e:
        logger.warning(f"EXCEPTION occurred: {e}")
        return False, f"EXCEPTION occurred"

def custom_is_email_allowed(email, any_bellingcat_email=False):
    return email.lower() in ALLOWED_EMAILS or (any_bellingcat_email and re.match(r'^[\w.]+@bellingcat\.com$', email))


#--------------------- Bearer Auth ANY EMAIL

async def get_bearer_auth_public(credentials: HTTPAuthorizationCredentials = Depends(bearer_security)):
    # validates the Bearer token in the case that it requires it
    access_token = credentials.credentials
    valid_user, info = authenticate_user_public(access_token)
    if valid_user: return info
    logger.debug(f"TOKEN FAILURE: {valid_user=} {info=}")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=info,
        headers={"WWW-Authenticate": "Bearer"},
    )
    
def authenticate_user_public(access_token):
    # https://cloud.google.com/docs/authentication/token-types#access
    if type(access_token)!=str or len(access_token)<10: return False, "invalid access_token"
    r = requests.get("https://oauth2.googleapis.com/tokeninfo", {"access_token":access_token})
    if r.status_code!=200: return False, "error occurred"
    try:
        j = r.json()
        if j.get("azp") != GOOGLE_CHROME_APP_ID_PUBLIC and j.get("aud")!=GOOGLE_CHROME_APP_ID_PUBLIC: 
            return False, f"token does not belong to correct APP_ID"
        if j.get("email_verified") != "true": 
            return False, f"email '{j.get('email')}' not verified"
        if int(j.get("expires_in", -1)) <= 0:
            return False, "Token expired"
        return True, j.get('email')
    except Exception as e:
        logger.warning(f"EXCEPTION occurred: {e}")
        return False, f"EXCEPTION occurred"

#--------------------- Basic Auth
SFP = os.environ.get("STATIC_FILE_PASSWORD", "") # min length is 20 chars
async def get_basic_auth(credentials: HTTPBasicCredentials = Depends(basic_security)):
    # validates that the Basic token in the case that it requires it
    assert len(SFP) >= 20, "Invalid STATIC_FILE_PASSWORD, must be at least 20 chars"
    current_password_bytes = credentials.password.encode("utf8")
    is_correct_password = secrets.compare_digest(current_password_bytes, SFP.encode("utf8"))
    if is_correct_password: return True
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Wrong static file access credentials",
        headers={"WWW-Authenticate": "Basic"}
    )