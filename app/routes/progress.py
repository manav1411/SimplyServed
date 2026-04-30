from flask import Blueprint, request, jsonify, current_app
from ..utils import load_progress, save_progress

bp = Blueprint("progress", __name__)
progress_data = {}

@bp.route("/progress", methods=["GET", "POST"])
def movie_progress():
    user = request.headers.get("Cf-Access-Authenticated-User-Email")
    if not user:
        abort(403)

    if request.method == "GET":
        movie = request.args.get("movie")
        return jsonify({"time": progress_data.get(user, {}).get(movie, 0)})

    data = request.get_json()
    movie, time = data["movie"], float(data["time"])

    if user not in progress_data:
        progress_data[user] = {}
    progress_data[user][movie] = time
    save_progress(current_app.config['PROGRESS_PATH'], progress_data)

    return jsonify({"status": "ok"})
