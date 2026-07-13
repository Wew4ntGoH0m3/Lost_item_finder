#!/bin/sh
set -eu

flask db upgrade
exec gunicorn --bind 0.0.0.0:8000 --workers "${GUNICORN_WORKERS:-2}" --threads "${GUNICORN_THREADS:-4}" --timeout 60 wsgi:app
