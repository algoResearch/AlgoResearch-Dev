from .pdf_field_mapping import field_positions  # Ensure field mapping exists

def generate_filled_pdf(pdf_path, output_pdf, form_data):
    
    print(f"Filled RR Budget PDF saved at {output_pdf}")
