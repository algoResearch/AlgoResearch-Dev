import requests
import xml.etree.ElementTree as ET
from django.core.management.base import BaseCommand
from dashboard.models import SF424Field

SF424_SCHEMA_URL = "https://apply07.grants.gov/apply/forms/schemas/SF424_4_0-V4.0.xsd"

def fetch_sf424_schema():
    """Downloads the SF-424 XML schema from Grants.gov"""
    response = requests.get(SF424_SCHEMA_URL)
    if response.status_code == 200:
        return response.content  # Return XML data as bytes
    else:
        raise Exception(f"❌ Failed to fetch XML schema. HTTP {response.status_code}")

def parse_sf424_schema(xml_data):
    """Extracts form fields from the SF-424 XML schema."""
    root = ET.fromstring(xml_data)  # Parse XML content
    ns = {"xs": "http://www.w3.org/2001/XMLSchema"}

    fields = []
    for element in root.findall(".//xs:element", ns):
        field_name = element.get("name")
        field_type = element.get("type") if element.get("type") else "string"

        # Check for dropdown values
        restriction = element.find(".//xs:restriction", ns)
        options = [enum.get("value") for enum in restriction.findall("xs:enumeration", ns)] if restriction else None

        fields.append({"name": field_name, "type": field_type, "options": options})

    return fields

class Command(BaseCommand):
    help = "Import SF-424 form fields from the Grants.gov XML schema"

    def handle(self, *args, **kwargs):
        try:
            self.stdout.write("📥 Fetching SF-424 XML schema...")
            xml_data = fetch_sf424_schema()
            fields = parse_sf424_schema(xml_data)

            for field in fields:
                SF424Field.objects.update_or_create(
                    name=field["name"],
                    defaults={"field_type": field["type"], "options": field["options"]}
                )

            self.stdout.write(self.style.SUCCESS(f"✅ Successfully imported {len(fields)} SF-424 fields"))
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error: {e}"))
