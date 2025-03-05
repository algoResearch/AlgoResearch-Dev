from django.core.management.base import BaseCommand
import pymupdf as fitz

class Command(BaseCommand):
    help = "Extract text and positions from a flattened PDF"

    def add_arguments(self, parser):
        parser.add_argument("pdf_path", type=str, help="Path to the PDF file")

    def handle(self, *args, **kwargs):
        pdf_path = kwargs["pdf_path"]
        self.extract_text_with_positions(pdf_path)

    def extract_text_with_positions(self, pdf_path):
        doc = fitz.open(pdf_path)
        for page_num, page in enumerate(doc):
            words = page.get_text("words")  # Extract all words with positions
            for w in words:
                x, y, text = w[0], w[1], w[4]  # Extract coordinates & text
                print(f"Page {page_num + 1}: '{text}' at ({x}, {y})")
