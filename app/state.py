import json
import os
import sqlite3
from datetime import datetime, timezone
from flask import current_app, g


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db():
    if "db" not in g:
        db = sqlite3.connect(current_app.config["DATABASE_PATH"])
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        db.execute("PRAGMA temp_store=MEMORY")
        g.db = db
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            display_name TEXT,
            created_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS movies (
            tmdb_id INTEGER PRIMARY KEY,
            folder_name TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            release_date TEXT,
            year TEXT,
            overview TEXT,
            genres_json TEXT NOT NULL DEFAULT '[]',
            runtime INTEGER,
            rating REAL,
            poster_path TEXT,
            media_filename TEXT,
            subtitles_filename TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS downloads (
            tmdb_id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            folder_name TEXT NOT NULL,
            status TEXT NOT NULL,
            requested_by_email TEXT,
            torrent_hash TEXT,
            torrent_name TEXT,
            progress REAL NOT NULL DEFAULT 0,
            state TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS playback_progress (
            user_email TEXT NOT NULL,
            movie_key TEXT NOT NULL,
            seconds REAL NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_email, movie_key)
        );
        """
    )
    ensure_column("downloads", "requested_by_email", "TEXT")
    db.commit()


def ensure_column(table, column, definition):
    columns = {row["name"] for row in get_db().execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        get_db().execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def record_user(email, display_name=None):
    now = utc_now()
    get_db().execute(
        """
        INSERT INTO users (email, display_name, created_at, last_seen_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
            display_name = COALESCE(excluded.display_name, users.display_name),
            last_seen_at = excluded.last_seen_at
        """,
        (email, display_name, now, now),
    )
    get_db().commit()


def get_progress(user_email, movie_key):
    row = get_db().execute(
        "SELECT seconds FROM playback_progress WHERE user_email = ? AND movie_key = ?",
        (user_email, movie_key),
    ).fetchone()
    return float(row["seconds"]) if row else 0.0


def set_progress(user_email, movie_key, seconds):
    get_db().execute(
        """
        INSERT INTO playback_progress (user_email, movie_key, seconds, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_email, movie_key) DO UPDATE SET
            seconds = excluded.seconds,
            updated_at = excluded.updated_at
        """,
        (user_email, movie_key, float(seconds), utc_now()),
    )
    get_db().commit()


def migrate_progress_json(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        current_app.logger.warning("Could not migrate playback progress from %s", path)
        return

    migrated = False
    for user_email, movies in data.items():
        if not isinstance(movies, dict):
            continue
        for movie_key, seconds in movies.items():
            existing = get_progress(user_email, movie_key)
            if existing == 0:
                set_progress(user_email, movie_key, seconds or 0)
                migrated = True
    if migrated:
        current_app.logger.info("Migrated playback progress from %s", path)


def find_media_filename(folder_path):
    for filename in sorted(os.listdir(folder_path)):
        if filename.lower().startswith("movie.") and filename.lower().endswith(".mp4"):
            return filename
    return None


def upsert_movie_from_folder(folder_name):
    folder_path = os.path.join(current_app.config["MEDIA_PATH"], folder_name)
    metadata_path = os.path.join(folder_path, "metadata.json")
    if not os.path.isdir(folder_path) or not os.path.exists(metadata_path):
        return None

    try:
        with open(metadata_path, encoding="utf-8") as f:
            metadata = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        current_app.logger.warning("Failed to read metadata for %s: %s", folder_name, exc)
        return None

    tmdb_id = metadata.get("tmdb_id")
    if not tmdb_id:
        return None

    now = utc_now()
    media_filename = find_media_filename(folder_path)
    subtitles_filename = "subtitles_1.vtt" if os.path.exists(os.path.join(folder_path, "subtitles_1.vtt")) else None
    release_date = metadata.get("release_date") or ""

    get_db().execute(
        """
        INSERT INTO movies (
            tmdb_id, folder_name, title, release_date, year, overview, genres_json,
            runtime, rating, poster_path, media_filename, subtitles_filename,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tmdb_id) DO UPDATE SET
            folder_name = excluded.folder_name,
            title = excluded.title,
            release_date = excluded.release_date,
            year = excluded.year,
            overview = excluded.overview,
            genres_json = excluded.genres_json,
            runtime = excluded.runtime,
            rating = excluded.rating,
            poster_path = excluded.poster_path,
            media_filename = excluded.media_filename,
            subtitles_filename = excluded.subtitles_filename,
            updated_at = excluded.updated_at
        """,
        (
            int(tmdb_id),
            folder_name,
            metadata.get("title") or folder_name,
            release_date,
            release_date[:4],
            metadata.get("overview") or "No description available.",
            json.dumps(metadata.get("genres") or []),
            metadata.get("runtime"),
            metadata.get("rating"),
            "poster.jpg" if os.path.exists(os.path.join(folder_path, "poster.jpg")) else None,
            media_filename,
            subtitles_filename,
            now,
            now,
        ),
    )
    get_db().commit()
    return get_movie(int(tmdb_id))


def sync_media_library():
    media_path = current_app.config["MEDIA_PATH"]
    os.makedirs(media_path, exist_ok=True)
    for folder_name in os.listdir(media_path):
        upsert_movie_from_folder(folder_name)


def get_movie(tmdb_id):
    return get_db().execute("SELECT * FROM movies WHERE tmdb_id = ?", (tmdb_id,)).fetchone()


def get_movie_by_folder(folder_name):
    return get_db().execute("SELECT * FROM movies WHERE folder_name = ?", (folder_name,)).fetchone()


def list_movies_for_user(user_email):
    rows = get_db().execute("SELECT * FROM movies WHERE media_filename IS NOT NULL ORDER BY title COLLATE NOCASE").fetchall()
    movies = []
    for row in rows:
        folder_name = row["folder_name"]
        seconds = get_progress(user_email, folder_name)
        runtime = row["runtime"] or 0
        duration_seconds = runtime * 60
        progress_percent = min(seconds / duration_seconds, 1) if duration_seconds > 0 else 0
        genres = json.loads(row["genres_json"] or "[]")
        movies.append(
            {
                "name": folder_name,
                "poster": f"/media_library/{folder_name}/poster.jpg" if row["poster_path"] else "",
                "progress_seconds": seconds,
                "progress_percent": progress_percent,
                "title": row["title"],
                "year": row["year"],
                "overview": row["overview"],
                "genres": genres,
                "runtime": runtime,
                "rating": row["rating"] or 0,
                "tmdb_id": row["tmdb_id"],
                "media_filename": row["media_filename"],
            }
        )
    movies.sort(key=lambda movie: movie["progress_percent"], reverse=True)
    return movies


def upsert_download(
    tmdb_id,
    title,
    folder_name,
    status,
    requested_by_email=None,
    torrent_hash=None,
    torrent_name=None,
    progress=0,
    state=None,
    error_message=None,
):
    now = utc_now()
    get_db().execute(
        """
        INSERT INTO downloads (
            tmdb_id, title, folder_name, status, requested_by_email, torrent_hash, torrent_name,
            progress, state, error_message, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tmdb_id) DO UPDATE SET
            title = excluded.title,
            folder_name = excluded.folder_name,
            status = excluded.status,
            requested_by_email = COALESCE(excluded.requested_by_email, downloads.requested_by_email),
            torrent_hash = COALESCE(excluded.torrent_hash, downloads.torrent_hash),
            torrent_name = COALESCE(excluded.torrent_name, downloads.torrent_name),
            progress = excluded.progress,
            state = excluded.state,
            error_message = excluded.error_message,
            updated_at = excluded.updated_at
        """,
        (
            tmdb_id,
            title,
            folder_name,
            status,
            requested_by_email,
            torrent_hash,
            torrent_name,
            progress,
            state,
            error_message,
            now,
            now,
        ),
    )
    get_db().commit()


def get_download(tmdb_id):
    return get_db().execute("SELECT * FROM downloads WHERE tmdb_id = ?", (tmdb_id,)).fetchone()


def get_download_by_title(title):
    normalized = "".join(ch for ch in title.lower() if ch.isalnum())
    rows = get_db().execute("SELECT * FROM downloads").fetchall()
    for row in rows:
        row_norm = "".join(ch for ch in row["title"].lower() if ch.isalnum())
        if normalized == row_norm:
            return row
    return None


def list_active_downloads():
    return get_db().execute(
        "SELECT * FROM downloads WHERE status IN ('requested', 'downloading', 'processing')"
    ).fetchall()


def delete_download(tmdb_id):
    get_db().execute("DELETE FROM downloads WHERE tmdb_id = ?", (tmdb_id,))
    get_db().commit()


def delete_movie_by_folder(folder_name):
    get_db().execute("DELETE FROM movies WHERE folder_name = ?", (folder_name,))
    get_db().commit()
