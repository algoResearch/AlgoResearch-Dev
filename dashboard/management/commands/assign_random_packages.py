# dashboard/management/commands/assign_random_packages.py
import random
from collections import OrderedDict
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from dashboard.models import Opportunity, FormPackage, PackageForm  # adjust import path if needed

# Canonical form types (keep keys in sync with PackageForm.FORM_TYPE_CHOICES)
FORM = OrderedDict([
    ("sf424", "SF-424"),
    ("rr_budget", "RR Budget"),
    ("phs_plan", "PHS Plan"),
    ("skp", "Senior Key Person"),
    ("site", "Project Site"),
    ("rr_other_info", "RR Other Info"),
    ("phs_cover", "PHS Cover"),
    ("phs_subjects", "PHS Human Subjects"),
])

# Template mapping per form_type
TEMPLATE_BY_TYPE = {
    "sf424":         "admin/fill_out_sf424.html",
    "rr_budget":     "admin/RR_Budget.html",
    "phs_plan":      "admin/fill_out_PHS_Plan.html",
    "skp":           "admin/senior_key_person_form.html",
    "site":          "admin/project_performance_site.html",
    "rr_other_info": "admin/RR_Other_Information.html",
    "phs_cover":     "admin/phs_cover_page.html",
    "phs_subjects":  "admin/phs_human_subjects.html",
}

# A small library of reusable package “archetypes”
PACKAGE_LIBRARY = [
    ("Basic",                ["sf424", "rr_other_info"]),
    ("Budgeted",             ["sf424", "rr_budget", "rr_other_info"]),
    ("Personnel & Budget",   ["sf424", "skp", "rr_budget", "rr_other_info"]),
    ("Clinical",             ["sf424", "phs_subjects", "rr_other_info"]),
    ("NIH Core",             ["sf424", "phs_cover", "skp", "rr_budget", "rr_other_info"]),
    ("NIH Full",             ["sf424", "phs_cover", "phs_plan", "skp", "rr_budget", "site", "rr_other_info"]),
    ("Research Basic",       ["sf424", "phs_plan", "rr_other_info"]),
    ("Site Heavy",           ["sf424", "site", "rr_budget", "rr_other_info"]),
]


def ensure_package_with_forms(name: str, form_types: list[str]) -> FormPackage:
    """
    Get or create a FormPackage with the given name and ensure it has exactly the
    listed form_types (in order). Also ensures html_template_name is set correctly.
    Idempotent across runs.
    """
    pkg, _ = FormPackage.objects.get_or_create(name=name)
    existing = {pf.form_type: pf for pf in pkg.package_forms.all().order_by("order")}

    # Create missing forms in correct order; preserve existing where possible
    order = 1
    touched_ids = set()
    for ft in form_types:
        wanted_template = TEMPLATE_BY_TYPE.get(ft)
        pf = existing.get(ft)
        if pf:
            updates = []
            if pf.order != order:
                pf.order = order
                updates.append("order")
            if pf.html_template_name != wanted_template:
                pf.html_template_name = wanted_template
                updates.append("html_template_name")
            if updates:
                pf.save(update_fields=updates)
        else:
            PackageForm.objects.create(
                package=pkg,
                form_type=ft,
                order=order,
                html_template_name=wanted_template,
            )
        touched_ids.add(ft)
        order += 1

    # Remove stray forms not in the target list (optional; comment out if you prefer to keep extras)
    for ft, pf in existing.items():
        if ft not in touched_ids:
            pf.delete()

    return pkg


def repair_all_package_form_templates() -> int:
    """
    Backfill/repair html_template_name for EVERY PackageForm in the database
    based on TEMPLATE_BY_TYPE. Returns the number of rows updated.
    """
    to_fix = []
    for pf in PackageForm.objects.all().only("id", "form_type", "html_template_name"):
        wanted = TEMPLATE_BY_TYPE.get(pf.form_type)
        if wanted and pf.html_template_name != wanted:
            pf.html_template_name = wanted
            to_fix.append(pf)
    if to_fix:
        PackageForm.objects.bulk_update(to_fix, ["html_template_name"])
    return len(to_fix)


class Command(BaseCommand):
    help = "Create random FormPackages, assign Opportunities to them, or repair existing package templates."

    def add_arguments(self, parser):
        parser.add_argument("--mode", choices=["templates", "per-opportunity"], default="templates",
                            help="templates=reuse a small library of packages (recommended); "
                                 "per-opportunity=create a unique package per opportunity (heavy).")
        parser.add_argument("--only-missing", action="store_true",
                            help="Only assign opportunities that currently have no form_package.")
        parser.add_argument("--limit", type=int, default=None,
                            help="Stop after assigning N opportunities (useful for testing).")
        parser.add_argument("--seed", type=int, default=42,
                            help="Random seed for reproducibility (templates mode).")

        # NEW: global repair flag
        parser.add_argument("--repair-templates", action="store_true",
                            help="Repair html_template_name for ALL existing PackageForms and exit.")

    @transaction.atomic
    def handle(self, *args, **opts):
        # If repair flag is set, do only the repair and exit
        if opts["repair_templates"]:
            fixed = repair_all_package_form_templates()
            self.stdout.write(self.style.SUCCESS(f"Repaired {fixed} PackageForm templates."))
            return

        mode = opts["mode"]
        only_missing = opts["only_missing"]
        limit = opts["limit"]
        seed = opts["seed"]

        # Build candidate opportunities queryset
        qs = Opportunity.objects.all()
        if only_missing:
            qs = qs.filter(form_package__isnull=True)

        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.WARNING("No opportunities to assign. (Maybe all already have a package?)"))
            return

        self.stdout.write(self.style.NOTICE(f"Mode: {mode} | only-missing={only_missing} | limit={limit or '∞'}"))
        self.stdout.write(self.style.NOTICE(f"Eligible opportunities: {total}"))

        assigned = 0
        created_packages = 0
        created_forms = 0  # just a soft count; we don’t track deletes/updates here

        if mode == "templates":
            # Seed deterministic randomness
            random.seed(seed)

            # Ensure library packages exist with proper forms + templates
            library_packages = []
            for name, form_types in PACKAGE_LIBRARY:
                pkg = ensure_package_with_forms(name, form_types)
                library_packages.append(pkg)

            # Assign opportunities
            for opp in qs.iterator(chunk_size=1000):
                pkg = random.choice(library_packages)
                if opp.form_package_id != pkg.id:
                    opp.form_package = pkg
                    opp.save(update_fields=["form_package"])
                assigned += 1
                if limit and assigned >= limit:
                    break

        else:  # per-opportunity (heavy)
            # For each opportunity, build a unique package with a random combo.
            # Rules: always include SF-424; then add 2–5 additional random forms.
            random.seed(seed)
            FORM_KEYS = list(FORM.keys())

            for opp in qs.iterator(chunk_size=500):
                # Create a unique package per opportunity
                pkg_name = f"PKG-{opp.number}"
                pkg, created = FormPackage.objects.get_or_create(name=pkg_name)
                if created:
                    created_packages += 1

                # Decide random combination
                base = ["sf424"]
                others = [k for k in FORM_KEYS if k != "sf424"]
                k = random.randint(2, 5)  # number of additional forms
                combo = base + random.sample(others, k=k)

                # Normalize and create/align PackageForms with defined order + templates
                existing = {pf.form_type: pf for pf in pkg.package_forms.all()}
                order = 1
                touched = set()
                for ft in combo:
                    wanted_template = TEMPLATE_BY_TYPE.get(ft)
                    pf = existing.get(ft)
                    if pf:
                        updates = []
                        if pf.order != order:
                            pf.order = order
                            updates.append("order")
                        if pf.html_template_name != wanted_template:
                            pf.html_template_name = wanted_template
                            updates.append("html_template_name")
                        if updates:
                            pf.save(update_fields=updates)
                    else:
                        PackageForm.objects.create(
                            package=pkg,
                            form_type=ft,
                            order=order,
                            html_template_name=wanted_template,
                        )
                        created_forms += 1
                    touched.add(ft)
                    order += 1

                # Remove stray forms (optional)
                for ft, pf in existing.items():
                    if ft not in touched:
                        pf.delete()

                # Assign to opportunity
                if opp.form_package_id != pkg.id:
                    opp.form_package = pkg
                    opp.save(update_fields=["form_package"])

                assigned += 1
                if limit and assigned >= limit:
                    break

        self.stdout.write(self.style.SUCCESS("\nAssignment summary"))
        self.stdout.write(self.style.SUCCESS(f"  Opportunities assigned: {assigned}"))
        if mode == "per-opportunity":
            self.stdout.write(self.style.SUCCESS(f"  Packages created:       {created_packages}"))
            self.stdout.write(self.style.SUCCESS(f"  PackageForms created:   {created_forms}"))