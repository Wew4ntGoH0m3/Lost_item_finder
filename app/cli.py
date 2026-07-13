import click
from flask.cli import with_appcontext

from .extensions import db


def register_cli(app):
    @app.cli.command("init-db")
    @with_appcontext
    def init_db():
        db.create_all()
        click.echo("Database tables created.")
