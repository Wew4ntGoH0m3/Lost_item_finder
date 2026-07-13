from celery import Celery, Task
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
migrate = Migrate()
jwt = JWTManager()
celery = Celery("lostlink")


def init_celery(app):
    celery.flask_app = app

    class FlaskTask(Task):
        def __call__(self, *args, **kwargs):
            with celery.flask_app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = FlaskTask
    celery.conf.update(
        broker_url=app.config["CELERY_BROKER_URL"],
        result_backend=app.config["CELERY_RESULT_BACKEND"],
        task_ignore_result=True,
        task_always_eager=app.config["CELERY_TASK_ALWAYS_EAGER"],
        task_eager_propagates=app.config["CELERY_TASK_EAGER_PROPAGATES"],
        broker_connection_retry_on_startup=True,
        timezone="UTC",
    )
    app.extensions["celery"] = celery
    return celery
