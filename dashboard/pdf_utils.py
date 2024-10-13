from PyPDF2 import PdfReader  # Replace PdfFileReader with PdfReader

def extract_pdf_fields(pdf_path):
    # Open the PDF file
    with open(pdf_path, "rb") as pdf_file:
        pdf_reader = PdfReader(pdf_file)  # Use PdfReader instead of PdfFileReader
        
        # Extract fields from the PDF
        fields = pdf_reader.get_fields()  # Use the new method for extracting fields
        return fields if fields else []
