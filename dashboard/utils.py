import xml.etree.ElementTree as ET
from .models import SF424Form
def generate_sf424_xml(sf424_instance):
    root = ET.Element("SF424Application")

    # Create sub-elements for each form field
    ET.SubElement(root, "SubmissionType").text = sf424_instance.submission_type
    ET.SubElement(root, "DateSubmitted").text = str(sf424_instance.date_submitted)
    ET.SubElement(root, "ApplicantIdentifier").text = sf424_instance.applicant_identifier or ""
    ET.SubElement(root, "StateApplicationIdentifier").text = sf424_instance.state_application_identifier or ""
    ET.SubElement(root, "FederalIdentifier").text = sf424_instance.federal_identifier or ""

    # Contact person details
    contact = ET.SubElement(root, "ContactPerson")
    ET.SubElement(contact, "FirstName").text = sf424_instance.contact_first_name
    ET.SubElement(contact, "LastName").text = sf424_instance.contact_last_name
    ET.SubElement(contact, "Email").text = sf424_instance.contact_email

    # Funding information
    funding = ET.SubElement(root, "EstimatedFunding")
    ET.SubElement(funding, "TotalFederalFundsRequested").text = str(sf424_instance.total_federal_funds_requested)
    ET.SubElement(funding, "TotalNonFederalFunds").text = str(sf424_instance.total_non_federal_funds)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
# your_app/utils.py
def get_base_template(user):
    if user.position_type in [
        'fund_manager', 'agency_user', 'nih_sro',
        'nih_chair', 'nih_board_member', 'admin', 'principal_admin'
    ]:
        return "admin/base_admin_dashboard.html"
    return "base_dashboard.html"