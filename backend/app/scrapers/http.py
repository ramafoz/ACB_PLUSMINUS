import httpx

DEFAULT_HEADERS = {
    "User-Agent": "ACB_PLUSMINUS/0.1 (manual scraper; contact: internal)"
}

def make_client() -> httpx.Client:
    # Keep it simple for now. We’ll add retries/throttling later.
    return httpx.Client(headers=DEFAULT_HEADERS, timeout=20.0, follow_redirects=True)
