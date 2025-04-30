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
from PIL import Image, ImageOps
from django.core.files.base import ContentFile
import io

def generate_group_photo(user_images, size=400):
    """
    Create a square group profile image using 2–4 user profile images.
    """
    num_images = min(len(user_images), 4)
    collage_size = (2, 2) if num_images > 1 else (1, 1)
    tile_width = size // collage_size[0]
    tile_height = size // collage_size[1]

    final_image = Image.new('RGB', (size, size), color='#f0f0f0')

    for idx, image_file in enumerate(user_images[:4]):
        try:
            img = Image.open(image_file).convert('RGB')
        except Exception:
            continue

        img = ImageOps.fit(img, (tile_width, tile_height), Image.ANTIALIAS)

        x = (idx % collage_size[0]) * tile_width
        y = (idx // collage_size[0]) * tile_height
        final_image.paste(img, (x, y))

    buffer = io.BytesIO()
    final_image.save(buffer, format='PNG')
    buffer.seek(0)
    return ContentFile(buffer.read(), name='group_photo.png')