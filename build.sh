#!/usr/bin/env bash
# Build script for Render deployment
set -o errexit

echo ">>> Installing dependencies..."
pip install -r requirements.txt

echo ">>> Collecting static files..."
python manage.py collectstatic --no-input

echo ">>> Running migrations..."
python manage.py migrate

echo ">>> Configuring site domain..."
python manage.py shell -c "
from django.contrib.sites.models import Site
import os
domain = os.environ.get('SITE_DOMAIN', 'localhost:8000')
name = os.environ.get('SITE_NAME', 'Finança')
Site.objects.update_or_create(pk=1, defaults={'domain': domain, 'name': name})
"

echo ">>> Build complete!"
