from PyPDF2 import PdfReader  # Replace PdfFileReader with PdfReader
# dashboard/core/pdf_utils.py

from PyPDF2 import PdfReader  # or whatever else you already import

try:
    from pdf2image import convert_from_path
except ImportError:  # pragma: no cover
    convert_from_path = None

def extract_pdf_fields(pdf_path):
    # Open the PDF file
    with open(pdf_path, "rb") as pdf_file:
        pdf_reader = PdfReader(pdf_file)  # Use PdfReader instead of PdfFileReader
        
        # Extract fields from the PDF
        fields = pdf_reader.get_fields()  # Use the new method for extracting fields
        return fields if fields else []
    
def convert_pdf_to_images(pdf_path: str, dpi: int = 200):
    """
    Convert a PDF into a list of PIL Image objects.

    Raises RuntimeError if pdf2image is not available.
    """
    if convert_from_path is None:
        raise RuntimeError("PDF-to-image conversion is not available (pdf2image not installed).")

    return convert_from_path(pdf_path, dpi=dpi)
