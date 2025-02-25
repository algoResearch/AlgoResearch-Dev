import json
import os
from adobe.pdfservices.operation.auth.credentials import Credentials
from adobe.pdfservices.operation.execution_context import ExecutionContext
from adobe.pdfservices.operation.io.file_ref import FileRef
from adobe.pdfservices.operation.pdfops.fill_acro_form import FillAcroFormOperation

# Load Adobe Credentials
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_PATH = os.path.join(BASE_DIR, "pdfservices-api-credentials.json")

def fill_sf424_form(input_pdf_path, output_pdf_path, form_data):
    """Fills out an SF-424 PDF using Adobe PDF Services API."""
    try:
        # Set up Adobe credentials
        credentials = Credentials.service_account_credentials_builder().from_file(CREDENTIALS_PATH).build()
        execution_context = ExecutionContext.create(credentials)

        # Load PDF
        input_pdf = FileRef.create_from_local_file(input_pdf_path)
        fill_form_operation = FillAcroFormOperation.create_new()
        fill_form_operation.set_input(input_pdf)

        # Populate fields
        fill_form_operation.set_form_field_values(form_data)

        # Save output PDF
        result = fill_form_operation.execute(execution_context)
        result.save_as(output_pdf_path)

        print(f"✅ SF-424 Form successfully filled: {output_pdf_path}")
        return output_pdf_path
    except Exception as e:
        print(f"❌ Error filling SF-424 form: {e}")
        return None
