import json

from flask import Blueprint, abort, jsonify, request

from ..state import get_progress, set_progress

bp = Blueprint("progress", __name__)


def progress_payload():
    data = request.get_json(silent=True)
    if data is not None:
        return data

    if request.data:
        try:
            return json.loads(request.data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
    return None


@bp.route("/progress", methods=["GET", "POST"])
def movie_progress():
    user = request.headers.get("Cf-Access-Authenticated-User-Email")
    if not user:
        abort(403)

    if request.method == "GET":
        movie = request.args.get("movie")
        if not movie:
            return jsonify({"error": "movie is required"}), 400
        return jsonify({"time": get_progress(user, movie)})

    data = progress_payload()
    if not data or "movie" not in data or "time" not in data:
        return jsonify({"error": "movie and time are required"}), 400

    set_progress(user, data["movie"], float(data["time"]))
    return jsonify({"status": "ok"})
