from dotenv import load_dotenv
from flask import Flask
import os

media_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'media_library'))
progress_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '.', 'user_progress.json'))
database_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '.', 'simplyserved.db'))

def create_app():
    load_dotenv(dotenv_path=os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env')))

    app = Flask(__name__)
    secret_key = os.getenv("FLASK_SECRET_KEY")
    if not secret_key and os.getenv("ALLOW_RANDOM_FLASK_SECRET") != "1":
        raise RuntimeError("FLASK_SECRET_KEY must be set. Use ALLOW_RANDOM_FLASK_SECRET=1 only for local throwaway dev.")
    app.secret_key = secret_key or os.urandom(32)
    app.config['MEDIA_PATH'] = media_path
    app.config['PROGRESS_PATH'] = progress_path
    app.config['DATABASE_PATH'] = os.getenv("DATABASE_PATH") or database_path
    app.config['ADMIN_EMAILS'] = {
        email.strip().lower()
        for email in (os.getenv("ADMIN_EMAILS") or "").split(",")
        if email.strip()
    }

    from .state import close_db, init_db, migrate_progress_json, sync_media_library
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
        migrate_progress_json(app.config['PROGRESS_PATH'])
        sync_media_library()

    from .auth import identify_user
    app.before_request(identify_user)

    from .routes import main, media, progress
    app.register_blueprint(main.bp)
    app.register_blueprint(media.bp)
    app.register_blueprint(progress.bp)

    return app
