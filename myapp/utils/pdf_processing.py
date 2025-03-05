import pymupdf as fitz
from .pdf_field_mapping import field_positions  # Ensure field mapping exists

def generate_filled_pdf(pdf_path, output_pdf, form_data):
    """Fills an RR Budget PDF with form data at specified positions"""
    doc = fitz.open(pdf_path)

    for page_num, page in enumerate(doc):
        for field, data in form_data.items():
            if field in field_positions:
                x, y = field_positions[field]
                page.insert_text((x, y), str(data), fontsize=10, color=(0, 0, 0))  # Insert text
    
    doc.save(output_pdf)
    print(f"Filled RR Budget PDF saved at {output_pdf}")
