from dashboard.models import AmendmentChangeLog, IACUCNote, IACUCSectionNote, IACUCSubmission
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
def auto_section_note(submission, section_id, field_label, old, new, author):
    if old != new:
        content = f"Changed {field_label} from '{old or '[blank]'}' to '{new or '[blank]'}'."
        IACUCNote.objects.create(
            submission=submission,
            section_id=section_id,
            content=content,
            author=author
        )
def log_section_changes(instance, form, section_id, user, submission):
    import logging
    logger = logging.getLogger(__name__)
    logger.warning("Running log_section_changes...")

    for field, new_val in form.cleaned_data.items():
        old_val = getattr(instance, field, None)

        # Convert to display values if choices exist
        field_obj = form.fields.get(field)
        if hasattr(field_obj, 'choices') and field_obj.choices:
            display_dict = dict(field_obj.choices)
            old_val_display = display_dict.get(old_val, old_val)
            new_val_display = display_dict.get(new_val, new_val)
        else:
            old_val_display = old_val
            new_val_display = new_val

        if old_val_display != new_val_display:
            label = field_obj.label or field.replace("_", " ").title()
            logger.warning(f"Logging change in {section_id}: {label} changed from {old_val_display} to {new_val_display}")
            IACUCNote.objects.create(
                submission=submission,
                author=user,
                section_id=section_id,
                content=f"Changed **{label}** from `{old_val_display or '[blank]'}` to `{new_val_display or '[blank]'}`"
            )