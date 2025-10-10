# utils.py or a shared location
def save_full_draft(project, org_id, package_id, user, sf424_data=None, rr_budget_data=None, budget_periods=None, cumulative_totals=None):
    draft, created = SubmittedPackage.objects.get_or_create(
        org_id=org_id,
        package_id=package_id,
        project=project,
        is_draft=True,
        defaults={
            "submission_name": f"Draft - {project.name}",
            "submission_date": timezone.now(),
            "last_edited_by": user
        }
    )

    if sf424_data is not None:
        draft.sf424_data = sf424_data
    if rr_budget_data is not None:
        draft.rr_budget_data = rr_budget_data
    if budget_periods is not None:
        draft.budget_periods = budget_periods
    if cumulative_totals is not None:
        draft.cumulative_totals = cumulative_totals

    draft.last_edited_by = user
    draft.save()
    return draft
