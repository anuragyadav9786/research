"""Master CLI orchestrator: for each active AMC in the AMC_Directory
sheet, runs its scraper (tier1 direct-link or tier2 Playwright), uploads
whatever real file it finds to the correct monthly Drive folder, and
logs the outcome to Monthly_Tracker.

Usage:
    python main.py [--month YYYY-MM] [--amc CODE1,CODE2] [--dry-run] [--force]

Defaults to the previous calendar month (config.current_reporting_month),
matching the scheduled run. An AMC with no registered scraper, or whose
scraper explicitly isn't implemented yet (see scrapers/tier1_direct.py,
scrapers/tier2_playwright.py), is logged as SKIPPED — never silently
dropped — so the catalog sheet always accounts for every AMC_Directory
row.
"""
from __future__ import annotations

import argparse
import tempfile

import config
from drive_manager import DriveManager, get_credentials
from scrapers.base_scraper import BaseScraper, ValidationError
from scrapers.tier1_direct import TIER1_SCRAPERS
from scrapers.tier2_playwright import TIER2_SCRAPERS
from tracker import AMCConfig, TrackerManager

SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {**TIER1_SCRAPERS, **TIER2_SCRAPERS}


def _run_one_amc(
    amc: AMCConfig,
    target_month: str,
    output_dir: str,
    drive: DriveManager | None,
    tracker: TrackerManager,
    month_folder_id: str | None,
    dry_run: bool,
) -> None:
    scraper_cls = SCRAPER_REGISTRY.get(amc.short_code)
    if scraper_cls is None:
        print(f"-- {amc.amc_name} ({amc.short_code}) -- no scraper registered, skipping")
        tracker.log_download_result(
            target_month, amc.amc_name, "", "", "", notes="No scraper registered for this Short Code", sync_status="Skipped"
        )
        return

    print(f"-- {amc.amc_name} ({amc.short_code}) --")
    scraper = scraper_cls()

    try:
        file_path = scraper.fetch_portfolio(target_month, output_dir)
    except NotImplementedError as exc:
        print(f"  {amc.short_code}: scraper not implemented yet — {exc}")
        tracker.log_download_result(
            target_month, amc.amc_name, "", "", "", notes=str(exc), sync_status="Skipped"
        )
        return
    except ValidationError as exc:
        print(f"  {amc.short_code}: downloaded file failed validation — {exc}")
        tracker.log_download_result(
            target_month, amc.amc_name, "", "", "", notes=str(exc), sync_status="Failed"
        )
        return
    except Exception as exc:
        print(f"  {amc.short_code}: scraper raised {type(exc).__name__}: {exc}")
        tracker.log_download_result(
            target_month, amc.amc_name, "", "", "", notes=f"{type(exc).__name__}: {exc}", sync_status="Failed"
        )
        return

    if file_path is None:
        print(f"  {amc.short_code}: no real file found for {target_month}")
        tracker.log_download_result(
            target_month, amc.amc_name, "", "", "", notes="No file found this month", sync_status="Not Found"
        )
        return

    file_name = file_path.rsplit("/", 1)[-1]

    if dry_run:
        print(f"  {amc.short_code}: [dry-run] would upload {file_name} and log to Monthly_Tracker")
        return

    assert drive is not None and month_folder_id is not None  # guaranteed by caller when not dry_run
    try:
        upload_result = drive.upload_portfolio_file(file_path, file_name, month_folder_id)
    except Exception as exc:
        print(f"  {amc.short_code}: Drive upload FAILED {type(exc).__name__}: {exc}")
        tracker.log_download_result(
            target_month, amc.amc_name, "", file_name, "", notes=f"Upload failed: {exc}", sync_status="Failed"
        )
        return

    drive_url = upload_result.get("web_view_link") or upload_result.get("file_id", "")
    print(f"  {amc.short_code}: uploaded {file_name} -> {drive_url}")
    tracker.log_download_result(
        target_month, amc.amc_name, "All Schemes", file_name, drive_url, sync_status="Pending"
    )


def run(target_month: str, amc_filter: list[str] | None, dry_run: bool, force: bool) -> None:
    print(f"Starting portfolio fetch for cycle: {target_month}" + (" [dry-run]" if dry_run else ""))

    credentials = get_credentials()
    tracker = TrackerManager(credentials)

    amc_directory = tracker.get_amc_directory()
    if amc_filter:
        wanted = {code.strip().upper() for code in amc_filter}
        amc_directory = [amc for amc in amc_directory if amc.short_code in wanted]
        missing = wanted - {amc.short_code for amc in amc_directory}
        if missing:
            print(f"Warning: --amc codes not found in AMC_Directory: {', '.join(sorted(missing))}")

    if not amc_directory:
        print("No AMCs to process (empty AMC_Directory, or --amc matched nothing).")
        return

    drive = None
    month_folder_id = None
    if not dry_run:
        drive = DriveManager(credentials)
        month_folder_id = drive.get_or_create_monthly_folder(target_month)
        print(f"Target Drive folder: {month_folder_id}")

    with tempfile.TemporaryDirectory(prefix="portfolio-fetcher-") as output_dir:
        for amc in amc_directory:
            if not force and tracker.is_already_downloaded(target_month, amc.short_code):
                print(f"-- {amc.amc_name} ({amc.short_code}) -- already downloaded this month, skipping (use --force to re-fetch)")
                continue
            _run_one_amc(amc, target_month, output_dir, drive, tracker, month_folder_id, dry_run)

    print("Done.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--month",
        help="Target month as YYYY-MM. Defaults to the previous calendar month "
        "(portfolios published in month N cover month N-1).",
    )
    parser.add_argument(
        "--amc",
        help="Comma-separated Short Codes to process (e.g. PPFAS,MIRAE). Defaults to every active AMC_Directory row.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run scrapers and report what would happen, without uploading to Drive or writing to Monthly_Tracker.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-fetch even if Monthly_Tracker already has a non-failed row for this month/AMC.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    month = args.month or config.current_reporting_month()
    amcs = args.amc.split(",") if args.amc else None
    run(month, amcs, args.dry_run, args.force)
