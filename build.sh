#!/usr/bin/env bash
# Build script for Render deployment
set -o errexit

echo ">>> Installing dependencies..."
pip install -r requirements.txt

echo ">>> Collecting static files..."
python manage.py collectstatic --no-input

echo ">>> Running migrations..."
python manage.py migrate

echo ">>> Build complete!"
