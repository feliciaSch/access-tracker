"""All settings come from environment variables, so the same code runs locally and on Render."""
import os


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:///./local.db")
    # Neon/Supabase hand you "postgresql://..." or "postgres://...".
    # SQLAlchemy needs to be told which driver to use (psycopg v3), so we rewrite the prefix.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DATABASE_URL = _database_url()

# Comma-separated list of frontend URLs allowed to call this API (CORS).
ALLOWED_ORIGINS = [
    o.strip().rstrip("/")
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if o.strip()
]

JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-change-me")
JWT_EXPIRES_MINUTES = int(os.getenv("JWT_EXPIRES_MINUTES", "480"))

# An approver account is created on startup from these, so you can log in and approve requests.
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

SENTRY_DSN = os.getenv("SENTRY_DSN")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
ENABLE_DEBUG_ROUTES = os.getenv("ENABLE_DEBUG_ROUTES", "true").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
APP_VERSION = os.getenv("RENDER_GIT_COMMIT", "local")[:7]
