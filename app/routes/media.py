from flask import Blueprint, send_from_directory, current_app

bp = Blueprint("media", __name__, url_prefix="/media_library")

@bp.route("/<path:filename>")
def serve_media(filename):
    # Production NGINX should serve this path directly. This route is a dev fallback.
    return send_from_directory(current_app.config['MEDIA_PATH'], filename)
