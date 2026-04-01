import requests


def scrape_website(url):
    """Scrape website content. Returns text or empty string on failure."""
    if not url:
        return ""
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return resp.text
    except Exception:
        return ""
