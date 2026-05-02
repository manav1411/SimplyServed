import os

import requests

from ..utils import normalize


class TMDbClient:
    def __init__(self, api_key=None, timeout=10):
        self.api_key = api_key or os.getenv("TMDB_API_KEY")
        self.timeout = timeout

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.api_key}"}

    def search_best_movie(self, query):
        response = requests.get(
            "https://api.themoviedb.org/3/search/movie",
            headers=self.headers,
            params={"query": query, "include_adult": False, "language": "en-US", "page": 1},
            timeout=self.timeout,
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        if not results:
            return None

        query_normalized = normalize(query)
        close_matches = [result for result in results if normalize(result.get("title", "")) == query_normalized]
        candidates = close_matches or results
        return max(candidates, key=lambda result: result.get("popularity", 0))

    def movie_details(self, tmdb_id):
        response = requests.get(
            f"https://api.themoviedb.org/3/movie/{tmdb_id}",
            headers=self.headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

