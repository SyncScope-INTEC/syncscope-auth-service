#!/bin/bash
set -e

# Collect static files at runtime when environment variables are available
python manage.py collectstatic --noinput

# Start gunicorn
exec gunicorn --config gunicorn.conf.py config.wsgi:application