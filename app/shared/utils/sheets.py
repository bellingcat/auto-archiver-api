"""Utilities for checking Google Sheet access permissions."""

from functools import lru_cache

import requests as http_requests
import yaml

from app.shared.log import logger


@lru_cache(maxsize=32)
def get_service_account_json_path(orchestrator_sheet_path: str) -> str | None:
    """
    Extract the service account JSON file path from an orchestrator sheet
    YAML config.

    Returns:
        Path to the service account JSON file, or None if not found.
    """
    if not orchestrator_sheet_path:
        return None

    try:
        with open(orchestrator_sheet_path) as f:
            orch = yaml.safe_load(f)
    except Exception as e:
        logger.warning(
            f"Could not read orchestrator sheet config {orchestrator_sheet_path}: {e}"
        )
        return None

    if not isinstance(orch, dict):
        return None

    def find_key(d: dict, key: str):
        for k, v in d.items():
            if k == key:
                return v
            if isinstance(v, dict):
                if result := find_key(v, key):
                    return result
        return None

    return find_key(orch, "service_account")


def check_sheet_write_access(
    service_account_json_path: str, sheet_id: str
) -> bool | None:
    """
    Check if a Google service account has write (Editor) access to a Google
    Sheet using the Google Drive API.

    Returns:
        True: Service account has write access.
        False: Service account does NOT have write access (or no access).
        None: Could not determine (network/auth error) — caller should
              proceed with archiving and let it fail naturally.
    """
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.service_account import Credentials

        creds = Credentials.from_service_account_file(
            service_account_json_path,
            scopes=["https://www.googleapis.com/auth/drive.metadata.readonly"],
        )
        creds.refresh(Request())

        resp = http_requests.get(
            f"https://www.googleapis.com/drive/v3/files/{sheet_id}",
            params={
                "fields": "capabilities/canEdit",
                "supportsAllDrives": "true",
            },
            headers={"Authorization": f"Bearer {creds.token}"},
            timeout=10,
        )

        if resp.status_code == 404:
            return False
        if resp.status_code == 403:
            return False
        if resp.status_code == 200:
            return resp.json().get("capabilities", {}).get("canEdit", False)

        logger.warning(
            f"Unexpected Drive API response {resp.status_code} for sheet {sheet_id}: {resp.text}"
        )
        return None

    except FileNotFoundError:
        logger.error(
            f"Service account JSON not found: {service_account_json_path}"
        )
        return None
    except Exception as e:
        logger.warning(
            f"Could not check write access for sheet {sheet_id}: {e}"
        )
        return None


def get_sheet_access_error(
    orchestrator_sheet_path: str | None,
    service_account_email: str | None,
    sheet_id: str,
) -> str | None:
    """
    Check if the service account has write access to a Google Sheet.

    Returns:
        An error message string if the sheet is NOT accessible, or None if
        access is OK (or the check is indeterminate).
    """
    if not orchestrator_sheet_path:
        return None

    sa_json_path = get_service_account_json_path(orchestrator_sheet_path)
    if not sa_json_path:
        return None

    has_access = check_sheet_write_access(sa_json_path, sheet_id)
    if has_access is False:
        sa_display = (
            service_account_email or "the Auto Archiver service account"
        )
        return (
            f"The Google Sheet has not been shared with the Auto Archiver "
            f"service account ({sa_display}). Please share the sheet with "
            f"this email address and give it Editor permissions."
        )
    return None
