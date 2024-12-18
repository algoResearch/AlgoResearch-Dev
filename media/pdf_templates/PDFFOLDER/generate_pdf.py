from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

def create_pdf(name, date, period, sky_color, bike_ridden):
    # Create a PDF file
    pdf_path = "filled_test_form.pdf"
    c = canvas.Canvas(pdf_path, pagesize=letter)
    width, height = letter

    # Add text to the PDF, positioned next to the questions
    c.drawString(100, height - 100, "Name: " + name)
    c.drawString(100, height - 130, "Date: " + date)
    c.drawString(100, height - 160, "Period: " + period)

    c.drawString(100, height - 200, "What color is the sky?")
    c.drawString(300, height - 200, sky_color)

    c.drawString(100, height - 240, "Did you ride your bike today?")
    c.drawString(300, height - 240, bike_ridden)

    # Save the PDF
    c.showPage()
    c.save()
    
    return pdf_path
