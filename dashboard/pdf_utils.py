from PyPDF2 import PdfReader  # Replace PdfFileReader with PdfReader
from pdf2image import convert_from_path
def extract_pdf_fields(pdf_path):
    # Open the PDF file
    with open(pdf_path, "rb") as pdf_file:
        pdf_reader = PdfReader(pdf_file)  # Use PdfReader instead of PdfFileReader
        
        # Extract fields from the PDF
        fields = pdf_reader.get_fields()  # Use the new method for extracting fields
        return fields if fields else []
def convert_pdf_to_images(pdf_path):
    """
    Convert a PDF file to a list of images (one per page).
    :param pdf_path: Path to the PDF file
    :return: List of PIL Image objects
    """
    images = convert_from_path(pdf_path)
    return images
