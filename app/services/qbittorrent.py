import os
import time

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

    def find_torrent(self, title=None, torrent_hash=None, save_path=None):
        save_path = save_path.rstrip("/") if save_path else None
        for torrent in self.torrents(category="media"):
            if torrent_hash and torrent.get("hash") == torrent_hash:
                return torrent
            if save_path:
                torrent_save_path = (torrent.get("save_path") or "").rstrip("/")
                content_path = (torrent.get("content_path") or "").rstrip("/")
                if torrent_save_path == save_path or content_path.startswith(save_path + "/") or content_path == save_path:
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

    def torrent_files(self, torrent_hash):
        self.login()
        response = self.session.get(
            f"{self.host}/api/v2/torrents/files",
            params={"hash": torrent_hash},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def wait_for_torrent(self, title=None, save_path=None, timeout_seconds=20):
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            torrent = self.find_torrent(title=title, save_path=save_path)
            if torrent and torrent.get("hash"):
                return torrent
            time.sleep(1)
        return self.find_torrent(title=title, save_path=save_path)

    def wait_for_files(self, torrent_hash, timeout_seconds=30):
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            files = self.torrent_files(torrent_hash)
            if files:
                return files
            time.sleep(1)
        return self.torrent_files(torrent_hash)

    def torrent_has_mp4(self, torrent_hash, timeout_seconds=30):
        files = self.wait_for_files(torrent_hash, timeout_seconds=timeout_seconds)
        return any(file.get("name", "").lower().endswith(".mp4") for file in files)
