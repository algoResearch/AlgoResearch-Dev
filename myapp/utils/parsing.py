from datetime import datetime

def parse_date(raw):
    if not raw:
        return None
    try:
        return datetime.strptime(raw, '%m%d%Y').date()
    except ValueError:
        return None
