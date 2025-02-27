import fitz  # PyMuPDF
import os

# Define input/output paths
input_pdf_path = "/Users/ryancarmody/algoResearchs/static/pdfs/SF424_4_0-V4.0X.pdf"
output_pdf_path = "/Users/ryancarmody/algoResearchs/static/pdfs/converted_sf424.pdf"

# Open the Reader-Enabled PDF
doc = fitz.open(input_pdf_path)

# Save a copy to remove restrictions
doc.save(output_pdf_path)

print("✅ Reader Rights Removed & New PDF Created:", output_pdf_path)
