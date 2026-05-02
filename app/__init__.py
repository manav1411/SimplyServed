from dotenv import load_dotenv
from flask import Flask
import os

media_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'media_library'))
progress_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '.', 'user_progress.json'))
database_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '.', 'simplyserved.db'))

def create_app():
    load_dotenv(dotenv_path=os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env')))

    app = Flask(__name__)
    default_secret = os.urandom(32)
    app.secret_key = os.getenv("FLASK_SECRET_KEY") or default_secret
    app.config['MEDIA_PATH'] = media_path
    app.config['PROGRESS_PATH'] = progress_path
    app.config['DATABASE_PATH'] = os.getenv("DATABASE_PATH") or database_path

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
