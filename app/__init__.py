import os

from flask import Flask, send_from_directory
from flask_cors import CORS

from .config import Config
from .errors import register_error_handlers
from .extensions import db, init_celery, jwt, migrate, socketio


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    socketio.init_app(
        app,
        async_mode="threading",
        cors_allowed_origins=app.config["SOCKET_CORS_ORIGINS"],
        message_queue=app.config["REDIS_URL"] or None,
    )
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    init_celery(app)

    from . import (
        models,  # noqa: F401
        tasks,  # noqa: F401
    )
    from .api import register_blueprints
    from .cli import register_cli
    from .socket_events import register_socket_events

    register_blueprints(app)
    register_error_handlers(app)
    register_cli(app)
    register_socket_events()

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/uploads/<path:filename>")
    def uploaded_file(filename):
        if not app.config["SERVE_UPLOADS"]:
            return {"error": "not found"}, 404
        return send_from_directory(app.config["UPLOAD_DIR"], filename)

    return app
