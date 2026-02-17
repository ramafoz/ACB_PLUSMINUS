import httpx
import time

DEFAULT_HEADERS = {
    "User-Agent": "ACB_PLUSMINUS/0.1 (manual scraper; contact: internal)"
}

def make_client() -> httpx.Client:
    # Give ACB more time; sometimes it stalls.
    timeout = httpx.Timeout(connect=10.0, read=40.0, write=10.0, pool=10.0)
    return httpx.Client(headers=DEFAULT_HEADERS, timeout=timeout, follow_redirects=True)

def get_with_retry(client: httpx.Client, url: str, retries: int = 1, backoff_s: float = 1.0) -> httpx.Response:
    last_exc = None
    for attempt in range(retries + 1):
        try:
            return client.get(url)
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.NetworkError) as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(backoff_s * (attempt + 1))
                continue
            raise
    raise last_exc  # type: ignore