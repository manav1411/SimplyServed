import os

import requests

from ..utils import normalize


class QBittorrentClient:
    def __init__(self, host=None, username=None, password=None, timeout=10):
        self.host = (host or os.getenv("QBITTORRENT_HOST") or "").rstrip("/")
        self.username = username or os.getenv("QBITTORRENT_USER")
        self.password = password or os.getenv("QBITTORRENT_PASS")
        self.timeout = timeout
        self.session = requests.Session()

    def login(self):
        response = self.session.post(
            f"{self.host}/api/v2/auth/login",
            data={"username": self.username, "password": self.password},
            timeout=self.timeout,
        )
        if response.status_code != 200 or response.text != "Ok.":
            raise RuntimeError("qBittorrent login failed")

    def add_torrent(self, magnet_uri, save_path):
        self.login()
        response = self.session.post(
            f"{self.host}/api/v2/torrents/add",
            data={"urls": magnet_uri, "savepath": save_path, "category": "media"},
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise RuntimeError("Failed to add torrent")

    def torrents(self, category=None):
        self.login()
        params = {"category": category} if category else None
        response = self.session.get(f"{self.host}/api/v2/torrents/info", params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def find_torrent(self, title=None, torrent_hash=None):
        for torrent in self.torrents(category="media"):
            if torrent_hash and torrent.get("hash") == torrent_hash:
                return torrent
            if title and normalize(title) in normalize(torrent.get("name", "")):
                return torrent
        return None

    def delete_torrent(self, torrent_hash):
        self.login()
        response = self.session.post(
            f"{self.host}/api/v2/torrents/delete",
            data={"hashes": torrent_hash, "deleteFiles": "true"},
            timeout=self.timeout,
        )
        response.raise_for_status()

