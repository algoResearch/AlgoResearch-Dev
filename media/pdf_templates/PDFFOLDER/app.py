from flask import Flask, render_template, request, send_file
from generate_pdf import create_pdf

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def form():
    if request.method == 'POST':
        # Capture the form data
        name = request.form.get('name')
        date = request.form.get('date')
        period = request.form.get('period')
        sky_color = request.form.get('sky_color')
        bike_ridden = request.form.get('bike_ridden')

        # Create the filled-out PDF
        pdf_path = create_pdf(name, date, period, sky_color, bike_ridden)
        
        # Serve the generated PDF for download
        return send_file(pdf_path, as_attachment=True)

    return render_template('form.html')

if __name__ == '__main__':
    app.run(debug=True)
