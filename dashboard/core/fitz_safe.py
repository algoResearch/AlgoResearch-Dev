# dashboard/core/fitz_safe.py
try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None
