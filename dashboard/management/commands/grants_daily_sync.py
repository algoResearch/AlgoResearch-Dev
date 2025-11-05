import os
import re
import io
import json
import zipfile
from pathlib import Path
from datetime import datetime, date
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.core.management import call_command

DATA_DIR = Path("data/grants")
STATE_FILE = DATA_DIR / "state.json"
XML_PAGE = "https://www.grants.gov/xml-extract"   

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return {}
    return {}

def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True))

def find_latest_zip_url(session: requests.Session) -> tuple[str, str]:
    """Return (zip_url, filename) for the newest GrantsDBExtract*.zip on the page."""
    resp = session.get(XML_PAGE, timeout=60)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    # Find any links to GrantsDBExtract*.zip (prefer v2 if present)
    candidates = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.search(r"GrantsDBExtract\d{8}(v2)?\.zip$", href, re.I):
            # absolute or relative
            url = href if href.startswith("http") else requests.compat.urljoin(XML_PAGE, href)
            candidates.append(url)
    if not candidates:
        raise CommandError("No GrantsDBExtract*.zip links found on the XML Extract page.")
    # simple sort by filename (yyyyMMdd + optional v2) – the page normally only shows one link
    candidates.sort(reverse=True)
    url = candidates[0]
    filename = url.split("/")[-1]
    return url, filename

def download_zip(session: requests.Session, url: str) -> Path:
    """Download ZIP into data/grants/<filename> if missing; return its path."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    local = DATA_DIR / url.split("/")[-1]
    if local.exists():
        return local
    with session.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(local, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
    return local

def unzip_xml(zip_path: Path) -> Path:
    """Extract the GrantsDBExtract*.xml from the zip to data/grants/, return xml path."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        xml_members = [m for m in zf.namelist() if m.lower().endswith(".xml")]
        if not xml_members:
            raise CommandError(f"No .xml found inside {zip_path.name}")
        # usually there is exactly one
        target_name = Path(xml_members[0]).name
        out_path = DATA_DIR / target_name
        # overwrite on purpose; importer is idempotent with --create-only
        with zf.open(xml_members[0]) as src, open(out_path, "wb") as dst:
            dst.write(src.read())
        return out_path

class Command(BaseCommand):
    help = "Daily sync: fetch newest GrantsDBExtract zip, import only still-open opportunities (create-only), then assign packages."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--dry-run", action="store_true", help="Run without DB writes (imports will use --dry-run).")
        parser.add_argument("--close-after", type=str, default=None,
                            help="Override cutoff date YYYY-MM-DD (default: today in America/New_York).")
        parser.add_argument("--force", action="store_true",
                            help="Ignore state file; process even if the newest filename matches last run.")
        parser.add_argument("--assign", action="store_true",
                            help="Also assign packages to unassigned opportunities after import (templates mode).")
        parser.add_argument("--user-agent", type=str, default="algoResearchs-grants-sync/1.0",
                            help="Custom User-Agent for requests.")
        parser.add_argument("--timeout", type=int, default=600, help="HTTP timeout seconds for zip download (default 600).")

    def handle(self, *args, **opts):
        dry_run = opts["dry_run"]
        force = opts["force"]
        assign = opts["assign"]
        timeout = opts["timeout"]

        # Determine cutoff (close_after): default = “today” in ET (so we only include still-open opps)
        if opts["close_after"]:
            try:
                cutoff = datetime.strptime(opts["close_after"], "%Y-%m-%d").date()
            except ValueError as e:
                raise CommandError("--close-after must be YYYY-MM-DD") from e
        else:
            et_today = datetime.now(ZoneInfo("America/New_York")).date()
            cutoff = et_today

        self.stdout.write(self.style.NOTICE(f"Cutoff (close_after): {cutoff.isoformat()} (exclusive)"))
        self.stdout.write(self.style.NOTICE(f"Dry run: {dry_run} | Force: {force} | Assign packages: {assign}"))

        # 1) Discover latest zip on the XML Extract page
        s = requests.Session()
        s.headers["User-Agent"] = opts["user_agent"]
        zip_url, filename = find_latest_zip_url(s)

        self.stdout.write(self.style.NOTICE(f"Latest on page: {filename}"))
        state = load_state()
        last_processed = state.get("last_zip")

        if last_processed == filename and not force:
            self.stdout.write(self.style.WARNING(f"Already processed {filename}; use --force to reprocess. Exiting."))
            return

        # 2) Download zip (idempotent: skips if present)
        zip_path = download_zip(s, zip_url)
        self.stdout.write(self.style.NOTICE(f"Downloaded: {zip_path}"))

        # 3) Extract XML to data/grants/
        xml_path = unzip_xml(zip_path)
        self.stdout.write(self.style.NOTICE(f"Extracted XML: {xml_path}"))

        # 4) Import: only create new, only still-open (close_date > cutoff)
        import_kwargs = dict(
            file=str(xml_path),
            close_after=cutoff.isoformat(),
        )
        if dry_run:
            import_kwargs["dry_run"] = True
        else:
            import_kwargs["create_only"] = True
            import_kwargs["bulk_create"] = True

        self.stdout.write(self.style.NOTICE("Starting import_grants_xml…"))
        call_command("import_grants_xml", **import_kwargs)

        # 5) Optional: assign packages to any that don’t have one yet
        if assign and not dry_run:
            self.stdout.write(self.style.NOTICE("Assigning packages to unassigned opportunities…"))
            call_command("assign_random_packages", only_missing=True, mode="templates")

        # 6) Save state
        state["last_zip"] = filename
        state["last_run_et"] = datetime.now(ZoneInfo("America/New_York")).isoformat()
        save_state(state)

        self.stdout.write(self.style.SUCCESS(f"Done. Marked {filename} as processed."))