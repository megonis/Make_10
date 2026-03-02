from app import app, ensure_database

ensure_database()

# Vercel expects a module-level variable called `app`.
