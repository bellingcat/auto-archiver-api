VERSION = "0.9.2"

API_DESCRIPTION = """
#### API for the Auto-Archiver project, a tool to archive web pages and Google Sheets.

**Usage notes:**
- The API requires a Bearer token for most operations, which you can obtain by logging in with your Google account.
- You can use this API to archive single URLs or entire Google Sheets.
- Once you submit a URL or Sheet for archiving, the API will return a task_id that you can use to check the status of the archiving process. It works asynchronously.
"""
BREAKING_CHANGES = {"minVersion": "0.4.0", "message": "The latest update has breaking changes, please update the extension to the most recent version."}

# changing this will corrupt the database logic
ALLOW_ANY_EMAIL = "*"
