import os
from dotenv import load_dotenv

load_dotenv()

VERSION = "0.7.0"
API_DESCRIPTION = """
#### API for the Auto-Archiver project, a tool to archive web pages and Google Sheets.

**Usage notes:**
- The API requires a Bearer token for most operations, which you can obtain by logging in with your Google account.
- You can use this API to archive single URLs or entire Google Sheets. 
- Once you submit a URL or Sheet for archiving, the API will return a task_id that you can use to check the status of the archiving process. It works asynchronously.
"""

ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "chrome-extension://ondkcheoicfckabcnkdgbepofpjmjcmb,chrome-extension://ojcimmjndnlmmlgnjaeojoebaceokpdp").split(",")

BREAKING_CHANGES = {"minVersion": "0.3.1", "message": "The latest update has breaking changes, please update the extension to the most recent version."}

SERVE_LOCAL_ARCHIVE = os.environ.get("SERVE_LOCAL_ARCHIVE", "")

SQLALCHEMY_DATABASE_URL = os.environ.get("DATABASE_PATH")

REPEAT_COUNT_METRICS_SECONDS = 15

CHROME_APP_IDS = set([app_id.strip() for app_id in os.environ.get("CHROME_APP_IDS", "").split(",")])
BLOCKED_EMAILS = set([e.strip().lower() for e in os.environ.get("BLOCKED_EMAILS", "").split(",")])