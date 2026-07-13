from .auth import bp as auth_bp
from .categories import bp as categories_bp
from .chats import bp as chats_bp
from .found_posts import bp as found_posts_bp
from .lost_posts import bp as lost_posts_bp
from .matches import bp as matches_bp
from .uploads import bp as uploads_bp
from .users import bp as users_bp


def register_blueprints(app):
    prefix = "/api/v1"
    app.register_blueprint(auth_bp, url_prefix=f"{prefix}/auth")
    app.register_blueprint(users_bp, url_prefix=f"{prefix}/users")
    app.register_blueprint(categories_bp, url_prefix=f"{prefix}/categories")
    app.register_blueprint(chats_bp, url_prefix=f"{prefix}/chats")
    app.register_blueprint(uploads_bp, url_prefix=f"{prefix}/uploads")
    app.register_blueprint(lost_posts_bp, url_prefix=f"{prefix}/lost-posts")
    app.register_blueprint(found_posts_bp, url_prefix=f"{prefix}/found-posts")
    app.register_blueprint(matches_bp, url_prefix=f"{prefix}/matches")
