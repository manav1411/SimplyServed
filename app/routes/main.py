import os
import shutil
import threading

import requests
from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from ..auth import require_admin
from ..services.jackett import JackettClient
from ..services.qbittorrent import QBittorrentClient
from ..services.tmdb import TMDbClient
from ..state import (
    delete_download,
    delete_movie_by_folder,
    get_download,
    get_download_by_title,
    get_movie,
    get_movie_by_folder,
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
    return (
        getattr(request, "is_admin", False)
        or (download["requested_by_email"] and download["requested_by_email"].lower() == request.user_email.lower())
    )


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

    reconcile_active_downloads()
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
        is_admin=getattr(request, "is_admin", False),
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
    subtitles_file = f"/media_library/{movie_name}/{movie['subtitles_filename']}" if movie["subtitles_filename"] else ""
    mime_type = "video/mp4"
    return render_template(
        "movie.html",
        movie_name=movie_name,
        movie_file=movie_file,
        subtitles_file=subtitles_file,
        mime_type=mime_type,
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

    movie_data = TMDbClient().movie_details(tmdb_id)
    movie_title = movie_data["title"]
    folder_name = movie_title
    save_path = os.path.join(current_app.config["MEDIA_PATH"], folder_name)
    os.makedirs(save_path, exist_ok=True)
    upsert_download(
        tmdb_id,
        movie_title,
        folder_name,
        "requested",
        requested_by_email=requested_by_email,
        progress=0,
        state="requested",
    )

    try:
        candidates = JackettClient().search_torrents(movie_title, movie_data.get("release_date"))
        if not candidates:
            error = "No MP4 torrents found"
            upsert_download(
                tmdb_id,
                movie_title,
                folder_name,
                "failed",
                requested_by_email=requested_by_email,
                error_message=error,
            )
            return {"error": error}, 404

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
                        tmdb_id,
                        movie_title,
                        folder_name,
                        "downloading",
                        requested_by_email=requested_by_email,
                        torrent_hash=torrent_hash,
                        torrent_name=torrent.get("name") or candidate.get("Title"),
                        progress=torrent.get("progress", 0),
                        state=torrent.get("state") or "queued",
                    )
                    return {"status": "started", "title": movie_title, "attempts": attempted}

                last_error = f"Torrent did not contain an MP4: {torrent.get('name') or candidate.get('Title')}"
                current_app.logger.info(last_error)
                qbittorrent.delete_torrent(torrent_hash)
            except Exception as candidate_exc:
                last_error = str(candidate_exc)
                current_app.logger.warning("Torrent candidate failed for %s: %s", movie_title, candidate_exc)
                if torrent and torrent.get("hash"):
                    try:
                        qbittorrent.delete_torrent(torrent["hash"])
                    except Exception as delete_exc:
                        current_app.logger.warning("Failed to delete rejected torrent for %s: %s", movie_title, delete_exc)

        error = "No MP4 torrents found"
        if last_error:
            error = f"{error} after {attempted} attempts. Last issue: {last_error}"
        upsert_download(
            tmdb_id,
            movie_title,
            folder_name,
            "failed",
            requested_by_email=requested_by_email,
            error_message=error,
        )
        return {"error": error}, 404
    except Exception as exc:
        upsert_download(
            tmdb_id,
            movie_title,
            folder_name,
            "failed",
            requested_by_email=requested_by_email,
            error_message=str(exc),
        )
        raise


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
    return jsonify({"status": "cancelled"})


@bp.route("/controls_info")
def controls_info():
    media_path = current_app.config["MEDIA_PATH"]
    total_size = 0
    folders = []

    for folder in os.listdir(media_path):
        folder_path = os.path.join(media_path, folder)
        if os.path.isdir(folder_path):
            size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, filenames in os.walk(folder_path) for f in filenames)
            total_size += size
            folders.append({"name": folder, "size": round(size / (1024 * 1024), 2)})

    return jsonify({"total_size": round(total_size / (1024 * 1024), 2), "directories": folders})


@bp.route("/reset_search", methods=["POST"])
def reset_search():
    require_admin()
    session["searched_movies"] = []
    session.modified = True
    return "", 204


@bp.route("/delete_folder/<folder>", methods=["POST"])
def delete_folder(folder):
    require_admin()
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
    return "", 204
