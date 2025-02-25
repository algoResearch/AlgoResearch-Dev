from PyPDF2 import PdfReader

pdf_path = "/Users/ryancarmody/algoResearchs/static/pdfs/SF424_2_1-V2.1.pdf"
reader = PdfReader(pdf_path)

acroform = reader.trailer["/Root"].get("/AcroForm")  # Safely fetch AcroForm
xfa = acroform.get("/XFA") if acroform else None  # Fetch XFA only if AcroForm exists

if acroform:
    print("✅ PDF is an AcroForm-based fillable PDF.")
elif xfa:
    print("⚠️ PDF is an XFA-based form (not supported by most PDF tools).")
else:
    print("❌ No form fields found.")
