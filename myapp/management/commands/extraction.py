from django.core.management.base import BaseCommand
import pymupdf as fitz  # PyMuPDF
import re

class Command(BaseCommand):
    help = "Extract fields from a flattened PDF"

    def add_arguments(self, parser):
        parser.add_argument("pdf_path", type=str, help="Path to the PDF file")

    def handle(self, *args, **kwargs):
        pdf_path = kwargs["pdf_path"]
        extracted_data = self.extract_text_from_pdf(pdf_path)
        print("📄 Extracted Data:", extracted_data)

    def extract_text_from_pdf(self, pdf_path):
        doc = fitz.open(pdf_path)
        data = {}

        for page in doc:
            text = page.get_text("text")

            # Define form field patterns
            patterns = {
                "Organization Name": r"Organization Name:\s*(.*)",
                "UEI": r"UEI:\s*(.*)",
                "Street 1": r"Street1:\s*(.*)",
                "Street 2": r"Street2:\s*(.*)",
                "City": r"City:\s*(.*)",
                "County": r"County:\s*(.*)",
                "State": r"State:\s*(.*)",
                "Country": r"Country:\s*(.*)",
                "ZIP Code": r"ZIP/Postal Code:\s*(.*)",
                "Congressional District": r"Congressional District:\s*(.*)",
            }

            for field, pattern in patterns.items():
                match = re.search(pattern, text, re.MULTILINE)
                if match:
                    # Clean extracted value
                    value = match.group(1).strip()
                    value = re.sub(r'[*]', '', value)  # Remove stray '*'
                    value = value.replace("\n", " ")  # Merge multiline values
                    data[field] = value

        return data
