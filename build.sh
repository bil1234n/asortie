#!/usr/bin/env bash
# Exit on error
set -o errexit

echo "--- Starting Professional Build Process ---"

# 1. Install requirements
echo "Installing dependencies..."
pip install -r requirements.txt

# 2. Collect static files (CSS/Images)
echo "Collecting static files..."
python manage.py collectstatic --no-input

# 3. Enable PGVector Extension in the Database
# We do this before migrations so the database knows how to handle VectorFields
echo "Enabling PGVector extension..."
python manage.py shell -c "from django.db import connection; cursor = connection.cursor(); cursor.execute('CREATE EXTENSION IF NOT EXISTS vector;');"

# 4. Create Migrations
# Note: Ensure your apps have 'migrations/' folders with '__init__.py' in your GitHub
echo "Creating migrations..."
python manage.py makemigrations --no-input

# 5. Apply Migrations
echo "Applying migrations to database..."
python manage.py migrate --no-input

echo "--- Build Process Complete Successfully ---"
