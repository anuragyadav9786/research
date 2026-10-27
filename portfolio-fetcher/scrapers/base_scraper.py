"""Shared contract and file-validation logic for every AMC scraper.

A scraper's only job is "find this month's real portfolio file and save
it locally" — Drive upload, Sheets logging, and dedup/cooldown all live
one layer up (drive_manager.py / tracker.py / main.py), so a scraper
never needs real credentials and stays independently testable.
"""
from __future__ import annotations

import io
import os
import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass

# Real file-format magic bytes — confirmed standard signatures, not a
# guess: XLSX (and any modern Office file) is a ZIP archive, so it
# starts with the ZIP local-file-header signature; legacy XLS is an OLE2
# Compound File, which starts with this fixed 8-byte signature.
XLSX_MAGIC = b"PK\x03\x04"
XLS_MAGIC = b"\xd0\xcf\x11\xe0"

MIN_PORTFOLIO_FILE_SIZE_BYTES = 25_000


@dataclass
class ScrapedFile:
    """One real file a scraper found — `scheme_hint` is a short label
    for what the file covers (a scheme name, or "All Schemes" for a
    single consolidated workbook), used only for logging/display, never
    for identity matching."""

    content: bytes
    file_name: str
    scheme_hint: str = "All Schemes"


class ValidationError(ValueError):
    """A downloaded file failed real-file validation (wrong magic bytes,
    too small, or an expected-but-missing .xlsx inside a ZIP archive) —
    raised rather than silently accepted, so a scraper never hands a
    broken/placeholder/error-page download up the pipeline as if it were
    a real portfolio file."""


def validate_file_bytes(content: bytes) -> str:
    """Confirms `content` is a real .xlsx or .xls file by magic bytes and
    minimum size. Returns the detected extension (".xlsx" or ".xls").
    Raises ValidationError otherwise — e.g. an AMC's disclosure page
    sometimes serves an HTML error page with a 200 status and an
    .xlsx-looking URL; this catches that rather than uploading a broken
    "portfolio" file.
    """
    if len(content) <= MIN_PORTFOLIO_FILE_SIZE_BYTES:
        raise ValidationError(
            f"File is {len(content)} bytes, below the {MIN_PORTFOLIO_FILE_SIZE_BYTES}-byte minimum "
            "for a real portfolio workbook (likely an error page or empty response)."
        )
    if content.startswith(XLSX_MAGIC):
        return ".xlsx"
    if content.startswith(XLS_MAGIC):
        return ".xls"
    raise ValidationError(
        f"File does not start with a recognized .xlsx/.xls signature (got {content[:4]!r})."
    )


def extract_xlsx_from_zip(content: bytes) -> bytes | None:
    """Some AMCs compress several schemes' sheets into one ZIP archive
    instead of publishing a single workbook directly. If `content` is
    itself a ZIP (same PK\\x03\\x04 signature as .xlsx, so this must be
    tried deliberately, not inferred from validate_file_bytes alone) and
    contains exactly one .xlsx member, returns that member's bytes.
    Returns None if `content` isn't a ZIP, or doesn't contain exactly one
    .xlsx — multiple .xlsx members means the caller needs per-scheme
    handling it hasn't implemented yet, so this deliberately doesn't
    guess which one is "the" file.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            xlsx_members = [n for n in zf.namelist() if n.lower().endswith(".xlsx")]
            if len(xlsx_members) != 1:
                return None
            return zf.read(xlsx_members[0])
    except zipfile.BadZipFile:
        return None


def build_portfolio_filename(month_year_str: str, short_code: str, extension: str) -> str:
    """"[YYYY-MM]_[SHORT_CODE]_Portfolio.xlsx" — the naming convention
    specified for every scraped file, independent of whatever filename
    the AMC's own site used."""
    return f"[{month_year_str}]_{short_code}_Portfolio{extension}"


class BaseScraper(ABC):
    """One AMC's scraper. `short_code` must match the AMC_Directory
    sheet's Short Code column exactly — that's the join key tracker.py
    and main.py use to route an AMC_Directory row to its scraper."""

    short_code: str

    @abstractmethod
    def fetch_portfolio(self, target_month: str, output_dir: str) -> str | None:
        """Finds and downloads this AMC's real portfolio file for
        `target_month` ("YYYY-MM"), saves it under `output_dir` as
        "[YYYY-MM]_[SHORT_CODE]_Portfolio.xlsx" (via
        build_portfolio_filename + validate_file_bytes +, if needed,
        extract_xlsx_from_zip), and returns the saved file's local path.

        Returns None if no real file could be found this month (e.g. not
        yet published, or the AMC changed its page) — never a fabricated
        or placeholder path. Implementations should let validation
        failures raise ValidationError rather than catching and
        swallowing them, so main.py can log the real reason as NOT_FOUND
        vs. FAILED instead of a silent miss.
        """
        raise NotImplementedError

    def save_validated(self, content: bytes, target_month: str, output_dir: str) -> str:
        """Shared save path every concrete scraper should call once it
        has real file bytes in hand — validates, unwraps a single-member
        ZIP if needed, and writes the final file under the standard
        naming convention. Raises ValidationError on anything that isn't
        a real portfolio workbook.
        """
        try:
            extension = validate_file_bytes(content)
        except ValidationError:
            unwrapped = extract_xlsx_from_zip(content)
            if unwrapped is None:
                raise
            content = unwrapped
            extension = validate_file_bytes(content)

        os.makedirs(output_dir, exist_ok=True)
        file_name = build_portfolio_filename(target_month, self.short_code, extension)
        file_path = os.path.join(output_dir, file_name)
        with open(file_path, "wb") as f:
            f.write(content)
        return file_path


__all__ = [
    "BaseScraper",
    "ScrapedFile",
    "ValidationError",
    "validate_file_bytes",
    "extract_xlsx_from_zip",
    "build_portfolio_filename",
    "MIN_PORTFOLIO_FILE_SIZE_BYTES",
]
