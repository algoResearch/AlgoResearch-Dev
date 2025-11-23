"""
Tests for dashboard forms
"""
from django.test import TestCase
from dashboard.forms import DeviationAuthorizationForm


class DeviationAuthorizationFormTests(TestCase):
    """Test cases for DeviationAuthorizationForm"""

    def test_form_initialization(self):
        """Test that the form initializes correctly"""
        form = DeviationAuthorizationForm()
        self.assertIn('deviation_text', form.fields)
        self.assertFalse(form.fields['deviation_text'].required)
        self.assertEqual(form.fields['deviation_text'].label, 'Deviation Authorization Text')

    def test_form_valid_with_text(self):
        """Test that form is valid with deviation text"""
        form_data = {
            'deviation_text': 'This is a test deviation authorization text for the project.'
        }
        form = DeviationAuthorizationForm(data=form_data)
        self.assertTrue(form.is_valid())
        self.assertEqual(
            form.cleaned_data['deviation_text'],
            'This is a test deviation authorization text for the project.'
        )

    def test_form_valid_without_text(self):
        """Test that form is valid even without text (field is optional)"""
        form_data = {
            'deviation_text': ''
        }
        form = DeviationAuthorizationForm(data=form_data)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['deviation_text'], '')

    def test_form_widget_attributes(self):
        """Test that the textarea widget has correct attributes"""
        form = DeviationAuthorizationForm()
        widget = form.fields['deviation_text'].widget
        self.assertEqual(widget.attrs.get('class'), 'form-control')
        self.assertEqual(widget.attrs.get('rows'), 10)
        self.assertEqual(
            widget.attrs.get('placeholder'),
            'Enter deviation authorization text here...'
        )

    def test_form_accepts_long_text(self):
        """Test that form accepts long text input"""
        long_text = 'A' * 5000  # 5000 character text
        form_data = {
            'deviation_text': long_text
        }
        form = DeviationAuthorizationForm(data=form_data)
        self.assertTrue(form.is_valid())
        self.assertEqual(len(form.cleaned_data['deviation_text']), 5000)
