#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
exec .venv/bin/python manage.py runserver 0.0.0.0:8321
