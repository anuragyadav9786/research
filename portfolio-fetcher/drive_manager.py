"""Google Drive access with dual authentication — the actual fix for the
real August 2026 failure:

    HttpError 403 ... "Service Accounts do not have storage quota.
    Leverage shared drives or user OAuth"

PR #10 (commit 58c94dd) already added supportsAllDrives=True /
includeItemsFromAllDrives=True to every Drive call here, which is
necessary but NOT sufficient — those flags only matter once the
destination folder genuinely lives inside a Google Shared Drive. A
service account still has zero personal storage quota regardless of the
flags; if DRIVE_MONTHLY_PORTFOLIOS_PARENT_ID was never actually moved
into a real Shared Drive (a one-time manual Drive action, not a code
change — see README.md), every create() call keeps 403ing no matter
what the code does.

User OAuth2 credentials sidestep this entirely (the file is owned by the
real Google account's own storage quota), so that's now the PRIMARY
path. Service-account + Shared Drive remains a supported fallback for
anyone who has actually done that Drive move.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import tempfile
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

import config

logger = logging.getLogger(__name__)


class DriveAuthError(RuntimeError):
    """No usable credentials were found in the environment — neither an
    OAuth2 token nor a service-account key. Raised rather than silently
    falling through to an unauthenticated client that would fail later
    with a much less obvious error."""


def _load_oauth_credentials() -> Credentials | None:
    """Builds Credentials from GOOGLE_OAUTH_TOKEN_B64 (a base64-encoded
    token.json, Render's env editor handles one long value more reliably
    than a mounted file across redeploys) or a local GOOGLE_OAUTH_TOKEN_FILE
    / ./token.json for development. Returns None if neither is present —
    that's a normal "OAuth not configured, try the fallback" case, not an
    error by itself.
    """
    token_info: dict[str, Any] | None = None

    b64 = os.environ.get(config.GOOGLE_OAUTH_TOKEN_B64_ENV)
    if b64:
        try:
            token_info = json.loads(base64.b64decode(b64))
        except Exception as exc:
            raise DriveAuthError(
                f"{config.GOOGLE_OAUTH_TOKEN_B64_ENV} is set but could not be base64/JSON decoded: {exc}"
            ) from exc
    else:
        token_path = os.environ.get(config.GOOGLE_OAUTH_TOKEN_FILE_ENV, config.DEFAULT_OAUTH_TOKEN_FILE)
        if os.path.exists(token_path):
            with open(token_path, "r", encoding="utf-8") as f:
                token_info = json.load(f)

    if token_info is None:
        return None

    creds = Credentials.from_authorized_user_info(token_info, scopes=config.SCOPES)

    # A user OAuth token's access token is short-lived (typically ~1
    # hour) — this worker runs once a month, so it's essentially always
    # expired by the time it runs; the refresh_token (long-lived, part
    # of the same token.json) is what actually matters here.
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        logger.info("OAuth access token refreshed.")
    elif not creds.valid:
        raise DriveAuthError(
            "OAuth token present but not valid and has no refresh_token to renew it — "
            "re-run the one-time consent flow (see README.md) to generate a fresh token.json."
        )

    return creds


def _load_service_account_credentials() -> service_account.Credentials | None:
    """Fallback path — same as the pre-existing behavior, reading either
    the full JSON key as one env var or a mounted key file. Returns None
    if neither is present (not an error — the OAuth path may be in use
    instead)."""
    raw_json = os.environ.get(config.GOOGLE_SERVICE_ACCOUNT_JSON_ENV)
    if raw_json:
        try:
            info = json.loads(raw_json)
        except Exception as exc:
            raise DriveAuthError(
                f"{config.GOOGLE_SERVICE_ACCOUNT_JSON_ENV} is set but is not valid JSON: {exc}"
            ) from exc
        return service_account.Credentials.from_service_account_info(info, scopes=config.SCOPES)

    key_path = os.environ.get(config.GOOGLE_SERVICE_ACCOUNT_FILE_ENV, config.DEFAULT_SERVICE_ACCOUNT_FILE)
    if os.path.exists(key_path):
        return service_account.Credentials.from_service_account_file(key_path, scopes=config.SCOPES)

    return None


def get_credentials():
    """OAuth2 user credentials first (works against a personal "My
    Drive" folder with no Shared Drive setup required); falls back to
    the service-account key (requires the destination to actually be a
    Shared Drive — see module docstring). Raises DriveAuthError if
    neither is configured, rather than returning None and failing later
    with an opaque API error."""
    oauth_creds = _load_oauth_credentials()
    if oauth_creds is not None:
        logger.info("Using OAuth2 user credentials for Drive/Sheets access.")
        return oauth_creds

    service_creds = _load_service_account_credentials()
    if service_creds is not None:
        logger.info(
            "Using service-account credentials for Drive/Sheets access — requires the destination "
            "folder to already be inside a Google Shared Drive (see README.md)."
        )
        return service_creds

    raise DriveAuthError(
        f"No usable credentials found. Set either {config.GOOGLE_OAUTH_TOKEN_B64_ENV} "
        f"(preferred) or {config.GOOGLE_SERVICE_ACCOUNT_JSON_ENV}."
    )


class DriveManager:
    """Thin wrapper around the Drive v3 client — every call explicitly
    passes supportsAllDrives=True/includeItemsFromAllDrives=True so a
    Shared-Drive-based service-account setup keeps working, while OAuth2
    user credentials work identically against a personal "My Drive"
    folder without needing either flag to matter."""

    def __init__(self, credentials=None):
        self._credentials = credentials or get_credentials()
        self._service = build("drive", "v3", credentials=self._credentials)

    def get_or_create_monthly_folder(self, month_year_str: str) -> str:
        """Finds or creates a folder named "[YYYY-MM] Portfolios" inside
        DRIVE_MONTHLY_PORTFOLIOS_PARENT_ID. Exact-name match (not
        `contains`) so e.g. "2026-08" never matches a differently-named
        folder that happens to contain that substring. Idempotent: a
        second call for the same month returns the same folder id rather
        than creating a duplicate.
        """
        folder_name = f"[{month_year_str}] Portfolios"
        query = (
            f"'{config.DRIVE_MONTHLY_PORTFOLIOS_PARENT_ID}' in parents and name = '{folder_name}' "
            "and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        )
        results = (
            self._service.files()
            .list(q=query, fields="files(id, name)", supportsAllDrives=True, includeItemsFromAllDrives=True)
            .execute()
        )
        files = results.get("files", [])
        if files:
            return files[0]["id"]

        metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [config.DRIVE_MONTHLY_PORTFOLIOS_PARENT_ID],
        }
        folder = self._service.files().create(body=metadata, fields="id", supportsAllDrives=True).execute()
        return folder["id"]

    def _find_existing_file(self, destination_filename: str, folder_id: str) -> str | None:
        query = f"'{folder_id}' in parents and name = '{destination_filename}' and trashed = false"
        results = (
            self._service.files()
            .list(q=query, fields="files(id, name)", supportsAllDrives=True, includeItemsFromAllDrives=True)
            .execute()
        )
        files = results.get("files", [])
        return files[0]["id"] if files else None

    def upload_portfolio_file(
        self, local_path: str, destination_filename: str, folder_id: str, mimetype: str | None = None
    ) -> dict:
        """Idempotent upload: if a file named `destination_filename`
        already exists in `folder_id`, its media content is updated in
        place instead of creating a duplicate (e.g. a re-run after a
        scraper fix shouldn't leave two copies). Returns
        {"file_id": ..., "web_view_link": ...}.

        Deliberately does not grant "anyone with the link can view" —
        same reasoning as the code this replaces: these are the user's
        own private files, and the account already uploading them
        already has direct API access for later ingestion. Add explicit
        public-sharing only if a real use case needs it.
        """
        mimetype = mimetype or (
            config.XLSX_MIMETYPE if local_path.lower().endswith(".xlsx") else config.XLS_MIMETYPE
        )
        media = MediaFileUpload(local_path, mimetype=mimetype)

        existing_id = self._find_existing_file(destination_filename, folder_id)
        if existing_id:
            updated = (
                self._service.files()
                .update(fileId=existing_id, media_body=media, fields="id, webViewLink", supportsAllDrives=True)
                .execute()
            )
            logger.info("Updated existing Drive file %r (id=%s)", destination_filename, existing_id)
            return {"file_id": updated["id"], "web_view_link": updated.get("webViewLink")}

        metadata = {"name": destination_filename, "parents": [folder_id]}
        created = (
            self._service.files()
            .create(body=metadata, media_body=media, fields="id, webViewLink", supportsAllDrives=True)
            .execute()
        )
        logger.info("Uploaded new Drive file %r (id=%s)", destination_filename, created["id"])
        return {"file_id": created["id"], "web_view_link": created.get("webViewLink")}

    def upload_portfolio_bytes(
        self, file_bytes: bytes, destination_filename: str, folder_id: str, mimetype: str | None = None
    ) -> dict:
        """Convenience wrapper for callers holding file content in memory
        (e.g. a scraper's HTTP response) rather than an existing local
        path — writes to a temp file and delegates to
        upload_portfolio_file so there's exactly one upload/idempotency
        implementation, not two."""
        suffix = os.path.splitext(destination_filename)[1] or ".xlsx"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        try:
            return self.upload_portfolio_file(tmp_path, destination_filename, folder_id, mimetype)
        finally:
            os.remove(tmp_path)


__all__ = ["DriveManager", "DriveAuthError", "get_credentials", "HttpError"]
