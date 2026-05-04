import json
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests
from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from ..services.jackett import JackettClient
from ..services.qbittorrent import QBittorrentClient
from ..services.tmdb import TMDbClient
from ..state import (
    delete_download,
    delete_movie_by_folder,
    get_db,
    get_download,
    get_download_by_title,
    get_movie,
    get_movie_by_folder,
    get_progress,
    list_active_downloads,
    list_movies_for_user,
    sync_media_library,
    upsert_download,
    upsert_movie_from_folder,
)
from ..utils import download_poster_and_metadata, finalize_movie_folder, normalize, search_and_download_subtitle

bp = Blueprint("main", __name__)
MAX_SEARCH_RESULTS = 5
MAX_TORRENT_ATTEMPTS = 5

_download_executor = ThreadPoolExecutor(max_workers=2)

_controls_info_cache = {"data": None, "ts": 0.0}
_CONTROLS_CACHE_TTL = 60


def _invalidate_controls_cache():
    _controls_info_cache["data"] = None


def safe_media_folder(folder_name):
    media_path = os.path.realpath(current_app.config["MEDIA_PATH"])
    folder_path = os.path.realpath(os.path.join(media_path, folder_name))
    if not folder_path.startswith(media_path + os.sep):
        return None
    return folder_path


def request_card_from_tmdb(movie):
    return {
        "id": movie["id"],
        "title": movie.get("title") or "Unknown title",
        "release_date": movie.get("release_date") or "",
        "overview": movie.get("overview") or "",
        "poster_path": movie.get("poster_path"),
    }


def remove_requested_movie(tmdb_id):
    session["searched_movies"] = [m for m in session.get("searched_movies", []) if m.get("id") != tmdb_id]
    session.modified = True


def can_cancel_download(download):
    return True


def reconcile_active_downloads():
    active_downloads = list_active_downloads()
    if not active_downloads:
        return

    try:
        client = QBittorrentClient()
        torrents = client.torrents(category="media")
    except Exception as exc:
        current_app.logger.warning("Download reconciliation skipped: %s", exc)
        return

    for download in active_downloads:
        torrent = find_matching_torrent(torrents, download)
        if not torrent:
            continue

        progress = float(torrent.get("progress", 0))
        state = torrent.get("state")
        upsert_download(
            download["tmdb_id"],
            download["title"],
            download["folder_name"],
            "downloading" if progress < 1 else download["status"],
            requested_by_email=download["requested_by_email"],
            torrent_hash=torrent.get("hash"),
            torrent_name=torrent.get("name"),
            progress=progress,
            state=state,
        )
        if progress >= 1 and download["status"] != "processing":
            process_completed_download_async(dict(get_download(download["tmdb_id"])))


def find_matching_torrent(torrents, download):
    save_path = os.path.join(current_app.config["MEDIA_PATH"], download["folder_name"]).rstrip("/")
    for torrent in torrents:
        if download["torrent_hash"] and torrent.get("hash") == download["torrent_hash"]:
            return torrent
        torrent_save_path = (torrent.get("save_path") or "").rstrip("/")
        content_path = (torrent.get("content_path") or "").rstrip("/")
        if torrent_save_path == save_path or content_path == save_path or content_path.startswith(save_path + "/"):
            return torrent
        if normalize(download["title"]) in normalize(torrent.get("name", "")):
            return torrent
    return None


@bp.route("/", methods=["GET", "POST"])
def landing_page():
    if "searched_movies" not in session:
        session["searched_movies"] = []

    if request.method == "POST":
        query = request.form.get("query", "").strip()
        if query:
            try:
                match = TMDbClient().search_best_movie(query)
                if match:
                    card = request_card_from_tmdb(match)
                    if not any(m.get("id") == card["id"] for m in session["searched_movies"]):
                        if len(session["searched_movies"]) >= MAX_SEARCH_RESULTS:
                            session["searched_movies"].pop(0)
                        session["searched_movies"].append(card)
                        session.modified = True
                    result = start_download_for_tmdb(card["id"], requested_by_email=request.user_email)
                    if isinstance(result, tuple):
                        payload, _status_code = result
                        flash(payload.get("error", "Request failed"), "error")
                else:
                    flash("No TMDb match found.", "error")
            except requests.RequestException as exc:
                current_app.logger.error("Movie request failed for %s: %s", query, exc)
                flash("External movie service request failed.", "error")
            except Exception as exc:
                current_app.logger.exception("Unexpected movie request failure for %s: %s", query, exc)
                flash(str(exc), "error")
        return redirect(url_for("main.landing_page") + "#bottom")

    searched_movies = []
    for movie in session.get("searched_movies", []):
        state_payload = download_state_payload(movie["id"])
        state = state_payload["state"]
        if state != "completed":
            movie = dict(movie)
            movie["download_state"] = state
            movie["download_error"] = state_payload.get("error", "")
            searched_movies.append(movie)
    session["searched_movies"] = searched_movies
    session.modified = True

    return render_template(
        "index.html",
        user_name=request.user_name,
        movies=list_movies_for_user(request.user_email),
        searched_movies=searched_movies,
    )


@bp.route("/remove_movie/<int:movie_id>", methods=["POST"])
def remove_movie(movie_id):
    remove_requested_movie(movie_id)
    return "", 204


@bp.route("/movie/<movie_name>")
def movie_page(movie_name):
    movie = get_movie_by_folder(movie_name) or upsert_movie_from_folder(movie_name)
    if not movie:
        return "Movie not found", 404

    media_filename = movie["media_filename"] or "movie.mp4"
    if not media_filename.lower().endswith(".mp4"):
        return "Unsupported media format. Please request an MP4 copy.", 415
    movie_file = f"/media_library/{movie_name}/{media_filename}"

    subtitles_list = []
    subtitles_json_path = os.path.join(current_app.config["MEDIA_PATH"], movie_name, "subtitles.json")
    if os.path.exists(subtitles_json_path):
        try:
            with open(subtitles_json_path, encoding="utf-8") as f:
                subtitles_list = json.load(f)
        except (OSError, json.JSONDecodeError):
            pass

    first_subtitle = (
        f"/media_library/{movie_name}/{subtitles_list[0]['filename']}" if subtitles_list else ""
    )
    sub_base = f"/media_library/{movie_name}"

    mime_type = "video/mp4"
    return render_template(
        "movie.html",
        movie_name=movie_name,
        movie_file=movie_file,
        subtitles_file=first_subtitle,
        subtitles_list=subtitles_list,
        sub_base=sub_base,
        mime_type=mime_type,
    )


def _run_download_worker(app, tmdb_id, movie_title, folder_name, save_path, requested_by_email, release_date):
    with app.app_context():
        try:
            candidates = JackettClient().search_torrents(movie_title, release_date)
            if not candidates:
                shutil.rmtree(save_path, ignore_errors=True)
                upsert_download(
                    tmdb_id, movie_title, folder_name, "failed",
                    requested_by_email=requested_by_email,
                    error_message="No MP4 torrents found",
                )
                return

            qbittorrent = QBittorrentClient()
            attempted = 0
            last_error = None
            for candidate in candidates[:MAX_TORRENT_ATTEMPTS]:
                attempted += 1
                torrent = None
                try:
                    qbittorrent.add_torrent(candidate["MagnetUri"], save_path)
                    torrent = qbittorrent.wait_for_torrent(title=movie_title, save_path=save_path)
                    if not torrent:
                        last_error = "Torrent was added but could not be found in qBittorrent"
                        continue

                    torrent_hash = torrent.get("hash")
                    if qbittorrent.torrent_has_mp4(torrent_hash):
                        upsert_download(
                            tmdb_id, movie_title, folder_name, "downloading",
                            requested_by_email=requested_by_email,
                            torrent_hash=torrent_hash,
                            torrent_name=torrent.get("name") or candidate.get("Title"),
                            progress=torrent.get("progress", 0),
                            state=torrent.get("state") or "queued",
                        )
                        return

                    last_error = f"Torrent did not contain an MP4: {torrent.get('name') or candidate.get('Title')}"
                    app.logger.info(last_error)
                    qbittorrent.delete_torrent(torrent_hash)
                except Exception as candidate_exc:
                    last_error = str(candidate_exc)
                    app.logger.warning("Torrent candidate failed for %s: %s", movie_title, candidate_exc)
                    if torrent and torrent.get("hash"):
                        try:
                            qbittorrent.delete_torrent(torrent["hash"])
                        except Exception as delete_exc:
                            app.logger.warning("Failed to delete rejected torrent for %s: %s", movie_title, delete_exc)

            error = "No MP4 torrents found"
            if last_error:
                error = f"{error} after {attempted} attempts. Last issue: {last_error}"
            shutil.rmtree(save_path, ignore_errors=True)
            upsert_download(
                tmdb_id, movie_title, folder_name, "failed",
                requested_by_email=requested_by_email,
                error_message=error,
            )
        except Exception as exc:
            app.logger.exception("Download worker failed for %s: %s", movie_title, exc)
            shutil.rmtree(save_path, ignore_errors=True)
            upsert_download(
                tmdb_id, movie_title, folder_name, "failed",
                requested_by_email=requested_by_email,
                error_message=str(exc),
            )


def start_download_for_tmdb(tmdb_id, requested_by_email=None):
    existing_movie = get_movie(tmdb_id)
    if existing_movie and existing_movie["media_filename"]:
        upsert_download(
            tmdb_id,
            existing_movie["title"],
            existing_movie["folder_name"],
            "ready",
            requested_by_email=requested_by_email,
            progress=1,
            state="ready",
        )
        return {"status": "ready", "title": existing_movie["title"]}

    existing_download = get_download(tmdb_id)
    if existing_download and existing_download["status"] not in {"failed", "ready"}:
        return {"status": existing_download["status"], "title": existing_download["title"]}

    movie_data = TMDbClient().movie_details(tmdb_id)
    movie_title = movie_data["title"]
    folder_name = movie_title
    save_path = os.path.join(current_app.config["MEDIA_PATH"], folder_name)
    upsert_download(
        tmdb_id, movie_title, folder_name, "requested",
        requested_by_email=requested_by_email, progress=0, state="requested",
    )

    app = current_app._get_current_object()
    _download_executor.submit(
        _run_download_worker,
        app, tmdb_id, movie_title, folder_name, save_path,
        requested_by_email, movie_data.get("release_date"),
    )
    return {"status": "queued", "title": movie_title}


@bp.route("/start_download/<int:tmdb_id>", methods=["POST"])
def start_download(tmdb_id):
    try:
        result = start_download_for_tmdb(tmdb_id, requested_by_email=request.user_email)
    except requests.RequestException as exc:
        current_app.logger.error("Download start failed for %s: %s", tmdb_id, exc)
        return jsonify({"error": "External service request failed"}), 502
    except Exception as exc:
        current_app.logger.error("Download start failed for %s: %s", tmdb_id, exc)
        return jsonify({"error": str(exc)}), 500

    if isinstance(result, tuple):
        payload, status_code = result
        return jsonify(payload), status_code
    return jsonify(result)


def process_completed_download(download):
    if download["status"] == "ready":
        return

    try:
        base_path = os.path.join(current_app.config["MEDIA_PATH"], download["folder_name"])
        if not finalize_movie_folder(base_path, allowed_extensions=(".mp4",)):
            raise RuntimeError("Downloaded torrent did not contain a supported MP4 movie file")
        download_poster_and_metadata(download["tmdb_id"], base_path)
        search_and_download_subtitle(download["title"], base_path)
        upsert_movie_from_folder(download["folder_name"])
        upsert_download(
            download["tmdb_id"],
            download["title"],
            download["folder_name"],
            "ready",
            requested_by_email=download["requested_by_email"],
            torrent_hash=download["torrent_hash"],
            torrent_name=download["torrent_name"],
            progress=1,
            state="ready",
        )
    except Exception as exc:
        current_app.logger.exception("Post-processing failed for %s: %s", download["title"], exc)
        upsert_download(
            download["tmdb_id"],
            download["title"],
            download["folder_name"],
            "failed",
            requested_by_email=download["requested_by_email"],
            torrent_hash=download["torrent_hash"],
            torrent_name=download["torrent_name"],
            progress=1,
            state="failed",
            error_message=str(exc),
        )


def process_completed_download_async(download):
    if download["status"] in {"ready", "processing"}:
        return

    upsert_download(
        download["tmdb_id"],
        download["title"],
        download["folder_name"],
        "processing",
        requested_by_email=download["requested_by_email"],
        torrent_hash=download["torrent_hash"],
        torrent_name=download["torrent_name"],
        progress=1,
        state="processing",
    )

    app = current_app._get_current_object()

    def worker():
        with app.app_context():
            process_completed_download(dict(get_download(download["tmdb_id"])))

    threading.Thread(target=worker, daemon=True).start()


@bp.route("/download_status/<movie_title>")
def download_status(movie_title):
    download = get_download_by_title(movie_title)
    if not download:
        return jsonify({"error": "Download not found"}), 404

    if download["status"] == "ready":
        return jsonify({"progress": 1, "state": "ready"})
    if download["status"] == "processing":
        return jsonify({"progress": download["progress"] or 1, "state": "processing"})
    if download["status"] == "failed":
        return jsonify({"error": download["error_message"] or "Download failed"}), 500
    if download["status"] == "requested":
        return jsonify({"progress": 0, "state": "searching"})

    try:
        save_path = os.path.join(current_app.config["MEDIA_PATH"], download["folder_name"])
        torrent = QBittorrentClient().find_torrent(
            title=download["title"],
            torrent_hash=download["torrent_hash"],
            save_path=save_path,
        )
    except Exception as exc:
        current_app.logger.warning("qBittorrent status failed for %s: %s", download["title"], exc)
        return jsonify({"error": "qBittorrent status failed"}), 502

    if not torrent:
        return jsonify({"error": "Torrent not found"}), 404

    progress = float(torrent.get("progress", 0))
    state = torrent.get("state")
    upsert_download(
        download["tmdb_id"],
        download["title"],
        download["folder_name"],
        "downloading",
        requested_by_email=download["requested_by_email"],
        torrent_hash=torrent.get("hash"),
        torrent_name=torrent.get("name"),
        progress=progress,
        state=state,
    )
    download = get_download(download["tmdb_id"])

    if progress >= 1.0:
        process_completed_download_async(dict(download))
        progress = 1
        state = "processing"

    return jsonify({"progress": progress, "state": state})


def download_state_payload(tmdb_id):
    movie = get_movie(tmdb_id)
    if movie and movie["media_filename"]:
        return {"state": "completed"}

    download = get_download(tmdb_id)
    if not download:
        return {"state": "idle"}
    if download["status"] == "ready":
        return {"state": "completed"}
    if download["status"] == "failed":
        return {"state": "failed", "error": download["error_message"]}
    if download["status"] == "processing":
        return {"state": "processing"}
    if download["status"] in {"requested", "downloading"}:
        return {"state": "downloading"}
    return {"state": download["status"]}


@bp.route("/download_state/<int:tmdb_id>")
def download_state(tmdb_id):
    return jsonify(download_state_payload(tmdb_id))


@bp.route("/cancel_download/<int:tmdb_id>", methods=["POST"])
def cancel_download(tmdb_id):
    download = get_download(tmdb_id)
    if not download:
        remove_requested_movie(tmdb_id)
        return jsonify({"error": "not in progress"}), 404
    if not can_cancel_download(download):
        return jsonify({"error": "admin or requester access required"}), 403

    try:
        torrent_hash = download["torrent_hash"]
        if not torrent_hash:
            save_path = os.path.join(current_app.config["MEDIA_PATH"], download["folder_name"])
            torrent = QBittorrentClient().find_torrent(title=download["title"], save_path=save_path)
            torrent_hash = torrent.get("hash") if torrent else None
        if torrent_hash:
            QBittorrentClient().delete_torrent(torrent_hash)
    except Exception as exc:
        current_app.logger.warning("Failed to delete torrent for %s: %s", download["title"], exc)

    folder_path = safe_media_folder(download["folder_name"])
    if folder_path and os.path.exists(folder_path):
        shutil.rmtree(folder_path, ignore_errors=True)

    delete_download(tmdb_id)
    remove_requested_movie(tmdb_id)
    sync_media_library()
    _invalidate_controls_cache()
    return jsonify({"status": "cancelled"})


def _dir_size(path):
    total = 0
    with os.scandir(path) as it:
        for entry in it:
            if entry.is_file(follow_symlinks=False):
                total += entry.stat(follow_symlinks=False).st_size
            elif entry.is_dir(follow_symlinks=False):
                total += _dir_size(entry.path)
    return total


@bp.route("/controls_info")
def controls_info():
    now = time.monotonic()
    if _controls_info_cache["data"] is not None and now - _controls_info_cache["ts"] < _CONTROLS_CACHE_TTL:
        return jsonify(_controls_info_cache["data"])

    media_path = current_app.config["MEDIA_PATH"]
    total_size = 0
    folders = []

    with os.scandir(media_path) as it:
        for entry in it:
            if entry.is_dir(follow_symlinks=False):
                size = _dir_size(entry.path)
                total_size += size
                folders.append({"name": entry.name, "size": round(size / (1024 * 1024), 2)})

    result = {"total_size": round(total_size / (1024 * 1024), 2), "directories": folders}
    _controls_info_cache.update({"data": result, "ts": now})
    return jsonify(result)


@bp.route("/reset_search", methods=["POST"])
def reset_search():
    session["searched_movies"] = []
    session.modified = True
    return "", 204


@bp.route("/delete_folder/<folder>", methods=["POST"])
def delete_folder(folder):
    folder_path = safe_media_folder(folder)
    if not folder_path or not os.path.isdir(folder_path):
        return "Folder not found", 404

    try:
        torrent = QBittorrentClient().find_torrent(title=folder)
        if torrent:
            QBittorrentClient().delete_torrent(torrent["hash"])
    except Exception as exc:
        current_app.logger.warning("Failed to remove torrent for %s: %s", folder, exc)

    shutil.rmtree(folder_path, ignore_errors=True)
    movie = get_movie_by_folder(folder)
    if movie:
        delete_download(movie["tmdb_id"])
    delete_movie_by_folder(folder)
    _invalidate_controls_cache()
    return "", 204


@bp.route("/settings_stats")
def settings_stats():
    db = get_db()
    user_email = request.user_email

    total_seconds = float(
        db.execute(
            "SELECT COALESCE(SUM(seconds), 0) as t FROM playback_progress WHERE user_email = ?",
            (user_email,),
        ).fetchone()["t"]
    )
    movies_started = db.execute(
        "SELECT COUNT(*) as c FROM playback_progress WHERE user_email = ? AND seconds > 60",
        (user_email,),
    ).fetchone()["c"]
    total_movies = db.execute(
        "SELECT COUNT(*) as c FROM movies WHERE media_filename IS NOT NULL"
    ).fetchone()["c"]
    requests_made = db.execute(
        "SELECT COUNT(*) as c FROM downloads WHERE requested_by_email = ?",
        (user_email,),
    ).fetchone()["c"]

    genre_rows = db.execute(
        "SELECT genres_json FROM movies WHERE media_filename IS NOT NULL"
    ).fetchall()
    genre_counts = {}
    for row in genre_rows:
        try:
            for g in json.loads(row["genres_json"] or "[]"):
                genre_counts[g] = genre_counts.get(g, 0) + 1
        except (json.JSONDecodeError, TypeError):
            pass
    top_genres = sorted(genre_counts, key=genre_counts.get, reverse=True)[:3]

    return jsonify({
        "hours_watched": round(total_seconds / 3600, 1),
        "movies_started": movies_started,
        "total_movies": total_movies,
        "requests_made": requests_made,
        "top_genres": top_genres,
    })


@bp.route("/admin")
def admin_page():
    return render_template("admin.html")


@bp.route("/admin/data")
def admin_data():
    db = get_db()
    now_utc = datetime.now(timezone.utc)
    active_threshold = timedelta(minutes=5)

    users = db.execute("SELECT * FROM users ORDER BY last_seen_at DESC").fetchall()
    user_list = []
    for u in users:
        email = u["email"]

        try:
            last_seen = datetime.fromisoformat(u["last_seen_at"])
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            is_active = (now_utc - last_seen) < active_threshold
        except Exception:
            is_active = False

        total_seconds = float(db.execute(
            "SELECT COALESCE(SUM(seconds), 0) as t FROM playback_progress WHERE user_email = ?",
            (email,),
        ).fetchone()["t"])

        movies_started = db.execute(
            "SELECT COUNT(*) as c FROM playback_progress WHERE user_email = ? AND seconds > 60",
            (email,),
        ).fetchone()["c"]

        requests_made = db.execute(
            "SELECT COUNT(*) as c FROM downloads WHERE requested_by_email = ?",
            (email,),
        ).fetchone()["c"]

        currently_watching = None
        latest_progress = db.execute(
            """
            SELECT pp.movie_key, pp.updated_at, m.title
            FROM playback_progress pp
            LEFT JOIN movies m ON m.folder_name = pp.movie_key
            WHERE pp.user_email = ?
            ORDER BY pp.updated_at DESC
            LIMIT 1
            """,
            (email,),
        ).fetchone()
        if is_active and latest_progress:
            try:
                prog_updated = datetime.fromisoformat(latest_progress["updated_at"])
                if prog_updated.tzinfo is None:
                    prog_updated = prog_updated.replace(tzinfo=timezone.utc)
                if (now_utc - prog_updated) < active_threshold:
                    currently_watching = latest_progress["title"] or latest_progress["movie_key"]
            except Exception:
                pass

        progress_rows = db.execute(
            """
            SELECT pp.movie_key, pp.seconds, pp.updated_at, m.title, m.runtime
            FROM playback_progress pp
            LEFT JOIN movies m ON m.folder_name = pp.movie_key
            WHERE pp.user_email = ?
            ORDER BY pp.updated_at DESC
            """,
            (email,),
        ).fetchall()

        progress = []
        for r in progress_rows:
            runtime_sec = (r["runtime"] or 0) * 60
            pct = round(min(r["seconds"] / runtime_sec * 100, 100)) if runtime_sec > 0 else 0
            progress.append({
                "movie_key": r["movie_key"],
                "title": r["title"] or r["movie_key"],
                "seconds": round(r["seconds"]),
                "runtime_seconds": runtime_sec,
                "percent": pct,
                "updated_at": r["updated_at"],
            })

        user_list.append({
            "email": email,
            "name": u["display_name"] or email.split("@")[0],
            "created_at": u["created_at"],
            "last_seen_at": u["last_seen_at"],
            "is_active": is_active,
            "currently_watching": currently_watching,
            "total_hours": round(total_seconds / 3600, 1),
            "movies_started": movies_started,
            "requests_made": requests_made,
            "progress": progress,
        })

    download_rows = db.execute(
        """
        SELECT d.title, d.status, d.progress, d.state, d.error_message,
               d.requested_by_email, d.created_at, d.updated_at,
               u.display_name as requester_name
        FROM downloads d
        LEFT JOIN users u ON u.email = d.requested_by_email
        ORDER BY d.updated_at DESC
        LIMIT 30
        """
    ).fetchall()

    downloads = []
    for d in download_rows:
        downloads.append({
            "title": d["title"],
            "status": d["status"],
            "progress": d["progress"],
            "state": d["state"],
            "error_message": d["error_message"],
            "requested_by": d["requester_name"] or (d["requested_by_email"] or "").split("@")[0],
            "created_at": d["created_at"],
            "updated_at": d["updated_at"],
        })

    total_movies = db.execute(
        "SELECT COUNT(*) as c FROM movies WHERE media_filename IS NOT NULL"
    ).fetchone()["c"]

    return jsonify({
        "users": user_list,
        "downloads": downloads,
        "library": {"total_movies": total_movies},
    })


@bp.route("/movie_card/<int:tmdb_id>")
def movie_card(tmdb_id):
    movie_row = get_movie(tmdb_id)
    if not movie_row:
        return "", 404
    genres = json.loads(movie_row["genres_json"] or "[]")
    progress_seconds = get_progress(request.user_email, movie_row["folder_name"])
    runtime = movie_row["runtime"] or 0
    movie = {
        "name": movie_row["folder_name"],
        "title": movie_row["title"],
        "year": movie_row["year"],
        "overview": movie_row["overview"],
        "genres": genres,
        "runtime": runtime,
        "rating": movie_row["rating"] or 0,
        "poster": f"/media_library/{movie_row['folder_name']}/poster.jpg" if movie_row["poster_path"] else "",
        "progress_seconds": progress_seconds,
    }
    return render_template("movie_card.html", movie=movie)
