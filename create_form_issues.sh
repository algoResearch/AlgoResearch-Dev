#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Bulk-create GitHub issues for form names using GitHub CLI.

Prereqs:
  - Install GitHub CLI: https://cli.github.com/
  - Authenticate once:  gh auth login

Usage:
  export GH_REPO=OWNER/REPO     # or pass -R OWNER/REPO
  bash create_form_issues.sh [--dry-run] [-R OWNER/REPO] [--label "Forms"]

Flags:
  --dry-run          Print the issues that would be created, without creating them
  -R, --repo REPO    Target repo in OWNER/REPO format (overrides $GH_REPO)
  --label LABEL      Label to apply to created issues (default: "form-tracking")
USAGE
}

DRY_RUN="no"
REPO_ARG="${GH_REPO:-}"
LABEL="form-tracking"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN="yes"; shift ;;
    -R|--repo) REPO_ARG="$2"; shift 2 ;;
    --label) LABEL="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

if ! command -v gh >/dev/null 2>&1; then
  echo "Error: GitHub CLI 'gh' not found. Install from https://cli.github.com/" >&2
  exit 1
fi

if [[ -z "${REPO_ARG}" ]]; then
  echo "Error: Please set GH_REPO=OWNER/REPO or pass -R OWNER/REPO" >&2
  exit 1
fi

# === Exclusions (case-insensitive substring match) ===
EXCLUDES_RAW='
SF-424
RR Budget
PHS Research Plan
Senior Key Person
Project Performance Site
RR Other Information
PHS Cover Page
PHS Human Subjects
'

# === All form names (combined; duplicates OK—will be de-duped) ===
FORMS_RAW='
Form 13977 VITA Grant Budget Plan
Budget Information for Non-Construction Programs (SF-424A)
Project Abstract Summary
Grant Application Form for Project Objectives and Performance Measures Information
HUD Detailed Budget Form
FRA F 251 Applicant Financial Capability Questionnaire
Farm To School Grant Program (FSGP)
Objective Work Plan
Applicant and Recipient Assurances and Certifications (HUD-424B)
FRA F 30
USDA AD-3030
Application for Federal Assistance (SF-424)
AFRI PROJECT TYPE
HUD Applicant-Recipient Disclosure Report
Tax Counseling for the Elderly (TCE) Program Application Checklist and Contact Sheet
Project Abstract
Regional Food System Partnerships Program
USDA AD-1050
CD511 Form
USDA AD-1047
Disclosure of Lobbying Activities (SF-LLL)
NEH Institutional Profile
NFLP Program Specific Data Forms
HUD-52768
Assurances for Construction Programs (SF-424D)
USDA AD-1052
Grant Program Accounting System & Financial Capability Questionnaire (FNS-906)
ACH Vendor/Miscellaneous Payment Enrollment Form
USDA AD-1048
Contact Information for VITA and TCE Grant Programs
Attachments
Project/Performance Site Location(s)
Supplementary Cover Sheet for NEH Grant Programs
HUD-50153
Other Attachments Form
EPA KEY CONTACTS FORM
Key Contacts
Low Income Taxpayer Clinic (LITC) Detailed Budget Worksheet
ED SF424 Supplement
Supplementary Cover Sheet for NEH State Councils
ED General Education Provisions Act (GEPA) 427 Form
Protection of Human Subjects
Tax Counseling for the Elderly Program Application Plan
HUD-52651
Budget Information for Construction Programs (SF-424C)
Form 13978 Projected Operations VITA Grant Application
Grants.gov Lobbying Form
Budget Narrative Attachment Form
EPA Form 4700-4
Low Income Taxpayer Clinics (LITCs) Application Information
Low Income Taxpayer Clinic (LITC) Application Narrative
OZ Certification Form
NIFA Supplemental Information
Evidence Form
Scholarships for Disadvantaged Students Program Specific Data Forms
U.S. DEPARTMENT OF EDUCATION BUDGET INFORMATION NON-CONSTRUCTION PROGRAMS
Standardized Work Plan (SWP)
ED Abstract Form
USDA AD-1049
Assurances for Non-Construction Programs (SF-424B)
Project Narrative Attachment Form
PHS 398 Training Subaward Budget Attachment(s) Form
PHS Fellowship Supplemental Form
PHS 398 Cover Page Supplement
PHS 398 Career Development Award Supplemental Form
NSF Cover Page
R & R Subaward Budget Attachment(s) Form 10 YR 10 ATT
USDA AD-1052
SF424 (R & R)
PHS Additional Indirect Costs
Research and Related Senior/Key Person Profile (Expanded)
Research & Related Subaward Budget (Total Fed + Non-Fed) Attachment(s) Form
PHS 398 Modular Budget
Research & Related Budget 10YR
NSF Senior Key Person Profile (Expanded)
PHS Human Subjects and Clinical Trials Information
PHS Assignment Request Form
R & R Multi-Project Subaward Budget Attachment(s) Form 10YR 30ATT
SF-424 R&R Multi-Project Cover
USDA AD-1047
Research & Related Budget (Total Fed + Non-Fed)
NSF Deviation Authorization
PHS 398 Training Budget
Research & Related Subaward Budget (Total Fed + Non-Fed) 5 YR 30 ATT
R & R Subaward Budget Attachment(s) Form
USDA AD-1048
NSF Suggested Reviewers
Assurances for Non-Construction Programs (SF-424B - R & R)
SBIR/STTR Information
R & R Subaward Budget Attachment(s) Form 5 YR 30 ATT
Key Contacts
NASA - PI and AOR
ANE Program Specific Data Forms
Form RD 400-1 Equal Opportunity Agreement
PHS Inclusion Enrollment Report
Scholarships for Disadvantaged Students Program Specific Data Forms
Research & Related Senior/Key Person Profile
Research & Related Multi-Project 10 Year Budget
Research & Related Budget
PHS 398 Research Plan
Disclosure of Foreign Relationships
USDA AD-1050
Research & Related Personal Data
NASA - Other Project Information
R & R Subaward Budget Attachment(s) Form 10 YR 30 ATT
Research And Related Other Project Information
PHS 398 Research Training Program Plan
'

# --- De-duplicate FORMS and load into ALL_FORMS (Bash 3 compatible) ---
FORMS_FILTERED="$(printf '%s\n' "$FORMS_RAW" | awk '!seen[$0]++')"

OLDIFS="$IFS"; IFS=$'\n'
ALL_FORMS=($FORMS_FILTERED)
IFS="$OLDIFS"

# --- Lowercase EXCLUDES and load into EXCLUDES array (Bash 3 compatible) ---
EXCLUDES_FILTERED="$(printf '%s\n' "$EXCLUDES_RAW" | awk '{print tolower($0)}')"

OLDIFS="$IFS"; IFS=$'\n'
EXCLUDES=($EXCLUDES_FILTERED)
IFS="$OLDIFS"

should_exclude() {
  # lowercase via tr (no ${var,,} for Bash 3)
  local name_lc
  name_lc="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  local ex
  for ex in "${EXCLUDES[@]}"; do
    case "$name_lc" in
      *"$ex"*) return 0 ;;  # match -> exclude
    esac
  done
  return 1
}

CREATED=0
SKIPPED=0

for name in "${ALL_FORMS[@]}"; do
  # skip blank lines
  [[ -z "${name// }" ]] && continue

  if should_exclude "$name"; then
    echo "Skip (excluded): $name"
    SKIPPED=$((SKIPPED+1))
    continue
  fi

  title="$name"
  body=$(cat <<BODY
**Form:** $name

This issue tracks implementation and integration for this form:
- [ ] Schema mapping
- [ ] Field items definition
- [ ] Instruction text
- [ ] PDF template (if applicable)
- [ ] Validation & OMB metadata (if applicable)
- [ ] UI hook / route wiring

**Context**
Created via bulk loader.
BODY
)

  if [[ "$DRY_RUN" == "yes" ]]; then
    echo "DRY-RUN: gh issue create -R \"$REPO_ARG\" --title \"$title\" --label \"$LABEL\" --body '<body>'"
  else
    gh issue create -R "$REPO_ARG" --title "$title" --label "$LABEL" --body "$body"
  fi
  CREATED=$((CREATED+1))
done

echo
echo "Done. Created: $CREATED, Skipped: $SKIPPED (excluded patterns)."
