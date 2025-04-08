# dashboard/utils/packages.py

def get_included_form_templates(package):
    return [pf.html_template_name for pf in package.package_forms.all()]
