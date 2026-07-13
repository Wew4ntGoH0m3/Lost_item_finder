#!/bin/sh
set -eu

flask db upgrade
exec gunicorn --bind 0.0.0.0:8000 --workers "${GUNICORN_WORKERS:-1}" --threads "${GUNICORN_THREADS:-50}" --timeout 60 wsgi:app
