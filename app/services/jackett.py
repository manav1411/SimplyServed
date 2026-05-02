import os

import requests


class JackettClient:
    def __init__(self, api_key=None, base_url="http://localhost:9117", timeout=15):
        self.api_key = api_key or os.getenv("JACKETT_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def best_torrent(self, title, release_date=None):
        year = (release_date or "")[:4]
        query_text = title if title.lower() == "casablanca" or not year else f"{title} {year}"
        response = requests.get(
            f"{self.base_url}/api/v2.0/indexers/all/results",
            params={"apikey": self.api_key, "Query": query_text},
            timeout=self.timeout,
        )
        response.raise_for_status()
        results = response.json().get("Results", [])
        if not results:
            return None

        filtered = [result for result in results if "1080p" in result.get("Title", "").lower()]
        candidates = filtered or results
        candidates.sort(key=lambda result: result.get("Seeders", 0), reverse=True)
        return candidates[0]

