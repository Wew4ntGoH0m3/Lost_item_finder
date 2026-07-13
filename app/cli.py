import click
from flask.cli import with_appcontext
from werkzeug.security import generate_password_hash

from .extensions import db
from .models import User


def register_cli(app):
    @app.cli.command("init-db")
    @with_appcontext
    def init_db():
        db.create_all()
        click.echo("Database tables created.")

    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    @click.option("--nickname", default="관리자")
    @click.option("--site-code", required=True)
    @with_appcontext
    def create_admin(email, password, nickname, site_code):
        normalized_email = email.strip().lower()
        user = db.session.scalar(db.select(User).where(User.email == normalized_email))
        if user:
            user.password_hash = generate_password_hash(password)
            user.nickname = nickname
            user.site_code = site_code.strip().upper()
            user.role = "ADMIN"
            user.is_active = True
            message = "Admin user updated."
        else:
            db.session.add(
                User(
                    email=normalized_email,
                    password_hash=generate_password_hash(password),
                    nickname=nickname,
                    site_code=site_code.strip().upper(),
                    role="ADMIN",
                )
            )
            message = "Admin user created."
        db.session.commit()
        click.echo(message)
