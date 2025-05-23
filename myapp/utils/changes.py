from dashboard.models import AmendmentChangeLog
def log_change(submission, section_id, field_name, old_value, new_value, user):
    if str(old_value) != str(new_value):
        AmendmentChangeLog.objects.create(
            submission=submission,
            section_id=section_id,
            field_name=field_name,
            old_value=str(old_value),
            new_value=str(new_value),
            updated_by=user
        )