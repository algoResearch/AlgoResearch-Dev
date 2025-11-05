# dashboard/management/commands/import_grants_xml.py
import re
from pathlib import Path
from datetime import datetime
import xml.etree.ElementTree as ET

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from dashboard.models import Agency, Opportunity

# Grants.gov element names vary slightly by version
OPP_DETAIL_TAG_SUFFIXES = (
    "OpportunitySynopsisDetail_1_0",
    "OpportunitySynopsisDetail_1_1",
    "OpportunitySynopsisDetail_1_2",
    "OpportunitySynopsisDetail",  # fallback
)

DEFAULT_NS = "http://apply.grants.gov/system/OpportunityDetail-V1.0"


def parse_date_flexible(raw):
    """Return date() or None from a variety of Grants.gov formats."""
    if not raw:
        return None
    raw = raw.strip()
    candidates = [
        "%m%d%Y",     # MMDDYYYY
        "%Y-%m-%d",   # ISO
        "%m/%d/%Y",   # MM/DD/YYYY
        "%Y%m%d",     # YYYYMMDD
    ]
    for fmt in candidates:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    # try digits-only
    digits = re.sub(r"[^\d]", "", raw)
    for fmt in ("%m%d%Y", "%Y%m%d"):
        try:
            return datetime.strptime(digits, fmt).date()
        except ValueError:
            pass
    return None


def text_or_blank(elem, child_tag, ns=None):
    """Safe text lookup that works with or without namespaces."""
    if elem is None:
        return ""
    if ns:
        found = elem.find(f"{{{ns}}}{child_tag}")
        if found is not None and found.text:
            return found.text.strip()
    found = elem.find(child_tag)
    if found is not None and found.text:
        return found.text.strip()
    return ""


def unique_slug_from_name(name: str) -> str:
    """
    Generate a unique slug for Agency.slug given a name.
    Ensures uniqueness by appending -2, -3, ... as needed.
    """
    base = slugify(name) or "agency"
    slug = base
    i = 2
    while Agency.objects.filter(slug=slug).exists():
        slug = f"{base}-{i}"
        i += 1
    return slug


class Command(BaseCommand):
    help = "Import all opportunities and agencies from a Grants.gov XML export."

    def add_arguments(self, parser):
        parser.add_argument("--file", dest="file", required=True)
        parser.add_argument("--ns", dest="ns", default=DEFAULT_NS)
        parser.add_argument("--dry-run", dest="dry_run", action="store_true")
        parser.add_argument("--limit", dest="limit", type=int, default=None,
                            help="Only process the first N opportunities (useful for testing)")
        parser.add_argument("--sample", dest="sample", type=int, default=0,
                            help="Print the first N parsed opportunities for visual verification")
        parser.add_argument("--create-only", dest="create_only", action="store_true",
                            help="Only create new opportunities; skip updates")
        parser.add_argument("--bulk-create", dest="bulk_create", action="store_true",
                            help="When used with --create-only, use bulk_create for speed")
        parser.add_argument("--close-after", dest="close_after", type=str, default=None,
                            help="Only import opps with close_date AFTER this YYYY-MM-DD date (exclusive)")


    def handle(self, *args, **opts):
        xml_path = Path(opts["file"])
        ns = opts["ns"] or None
        dry_run = opts["dry_run"]
        limit = opts["limit"]
        sample = opts["sample"]
        create_only = opts["create_only"]
        bulk_create = opts["bulk_create"]
        close_after = opts["close_after"]
        cutoff_date = None
        if close_after:
            try:
                cutoff_date = datetime.strptime(close_after, "%Y-%m-%d").date()
            except ValueError as e:
                raise CommandError(f"--close-after must be YYYY-MM-DD (got {close_after!r})") from e

        if not xml_path.exists():
            raise CommandError(f"File not found: {xml_path}")

        self.stdout.write(self.style.NOTICE(f"Reading: {xml_path}"))
        self.stdout.write(self.style.NOTICE(f"Namespace: {ns or '(none)'}"))
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN mode."))

        # Regex to detect any matching opportunity detail tag (suffix-only, ns tolerant)
        tag_regex = re.compile(
            r".*(" + "|".join(re.escape(s) for s in OPP_DETAIL_TAG_SUFFIXES) + r")$"
        )

        created_agencies = 0
        updated_agencies = 0
        touched_opps = 0
        created_opps = 0
        updated_opps = 0
        skipped_empty_number = 0

        # Simple in-memory cache to reduce DB lookups
        # Keys: agency_code or agency_name
        agency_cache = {}

        ctxt = ET.iterparse(str(xml_path), events=("start", "end"))
        _, root = next(ctxt)  # root element
        processed = 0
        to_create = []
        BATCH = 1000
        existing_numbers = set()
        if not dry_run and create_only:
            existing_numbers = set(
                Opportunity.objects.values_list("number", flat=True)
           )
        def process():
            nonlocal created_agencies, updated_agencies, touched_opps, created_opps, updated_opps, skipped_empty_number, processed, sample
            for event, elem in ctxt:
                if event != "end":
                    continue
                if not tag_regex.match(elem.tag):
                    continue

                # extract with/without ns
                get = lambda tag: text_or_blank(elem, tag, ns=ns)

                number = (get("OpportunityNumber") or "").strip()[:100]
                if not number:
                    skipped_empty_number += 1
                    elem.clear()
                    root.clear()
                    continue

                title = (get("OpportunityTitle") or "Untitled Opportunity").strip()[:255]
                agency_name = (get("AgencyName") or "").strip()[:255]
                agency_code = (get("AgencyCode") or "").strip()[:100]  # we'll store in Agency.internal_code
                category_expl = (get("CategoryExplanation") or "").strip()[:255]
                cfda = (get("CFDANumbers") or "").strip()[:100]
                open_date = parse_date_flexible(get("PostDate"))
                close_date = parse_date_flexible(get("CloseDate"))
                if cutoff_date:
                    if not close_date or close_date <= cutoff_date:
                        # skip old/closed items
                        elem.clear()
                        root.clear()
                        continue
                if sample and processed < sample:
                    self.stdout.write(
                        f"[SAMPLE #{processed+1}] "
                        f"number={number!r} | title={title[:80]!r} | "
                        f"agency_name={agency_name!r} | agency_code={agency_code!r} | "
                        f"cfda={cfda!r} | open_date={open_date} | close_date={close_date}"
                    )

                # --- Resolve/Create Agency ---
                agency_obj = None
                agency_key = (agency_code or agency_name or "").strip()
                if agency_key:
                    if agency_key in agency_cache:
                        agency_obj = agency_cache[agency_key]
                    else:
                        if not dry_run:
                            # Prefer match by internal_code if present; otherwise by name
                            if agency_code:
                                agency_obj = Agency.objects.filter(internal_code=agency_code).first()
                                if agency_obj is None and agency_name:
                                    agency_obj = Agency.objects.filter(name=agency_name).first()
                            else:
                                agency_obj = Agency.objects.filter(name=agency_name).first()

                            if agency_obj is None:
                                # Create new agency with safe unique slug
                                agency_obj = Agency.objects.create(
                                    name=agency_name or agency_code or "Unknown Agency",
                                    slug=unique_slug_from_name(agency_name or agency_code or "Unknown Agency"),
                                    internal_code=agency_code or None,
                                )
                                created_agencies += 1
                            else:
                                # Backfill/refresh internal_code if we have a better value
                                if agency_code and agency_obj.internal_code != agency_code:
                                    agency_obj.internal_code = agency_code
                                    agency_obj.save(update_fields=["internal_code"])
                                    updated_agencies += 1

                        agency_cache[agency_key] = agency_obj

                # --- Upsert Opportunity by number ---
                # --- Upsert/Create Opportunity by number ---
                if dry_run:
                    touched_opps += 1
                else:
                    defaults = {
                        "title": title,
                        "comp_id": agency_code,       # AgencyCode
                        "comp_title": category_expl,  # CategoryExplanation
                        "agency_ref": agency_obj,
                        "cfda": cfda,
                        "open_date": open_date,
                        "close_date": close_date,
                    }

                    if create_only:
                        # only create if missing; skip updates
                        if number not in existing_numbers:
                            if bulk_create:
                                to_create.append(Opportunity(number=number, **defaults))
                                if len(to_create) >= BATCH:
                                    Opportunity.objects.bulk_create(to_create, ignore_conflicts=True)
                                    created_opps += len(to_create)
                                    to_create.clear()
                            else:
                                Opportunity.objects.create(number=number, **defaults)
                                created_opps += 1
                            existing_numbers.add(number)  # keep set current during this run
                        # counted as touched regardless
                        touched_opps += 1
                    else:
                        obj, created = Opportunity.objects.update_or_create(
                            number=number,
                            defaults=defaults,
                        )
                        touched_opps += 1
                        if created:
                            created_opps += 1
                        else:
                            updated_opps += 1
                processed += 1
                if processed % 100 == 0:
                    self.stdout.write(f"…processed {processed} opportunities")
                if limit and processed >= limit:
                    # clean up current nodes then stop
                    elem.clear()
                    root.clear()
                    break
                # memory cleanup
                elem.clear()
                root.clear()

        try:
            process()
            if not dry_run and create_only and bulk_create and to_create:
                Opportunity.objects.bulk_create(to_create, ignore_conflicts=True)
                created_opps += len(to_create)
                to_create.clear()
        except Exception as e:
            raise CommandError(f"Import failed: {e}") from e

        # Summary
        hdr = "DRY RUN summary" if dry_run else "Import summary"
        self.stdout.write(self.style.SUCCESS(f"\n{hdr}"))
        self.stdout.write(self.style.SUCCESS(f"  Agencies created:      {created_agencies}"))
        if updated_agencies:
            self.stdout.write(self.style.SUCCESS(f"  Agencies updated:      {updated_agencies}"))
        self.stdout.write(self.style.SUCCESS(f"  Opportunities touched: {touched_opps}"))
        self.stdout.write(self.style.SUCCESS(f"    ├─ created:          {created_opps}"))
        self.stdout.write(self.style.SUCCESS(f"    └─ updated:          {updated_opps}"))
        if skipped_empty_number:
            self.stdout.write(self.style.WARNING(f"  Skipped (no number):   {skipped_empty_number}"))
