"""Database connection utilities."""
import os
import psycopg2


def get_db_connection():
    """
    Get database connection using environment variables.

    Priority:
    1. PG_DSN environment variable (full connection string)
    2. Individual components: PG_USER, PG_PASS, PG_HOST, PG_PORT, PG_DB

    Raises:
        ValueError: If database credentials are not configured.

    Returns:
        psycopg2.connection: Database connection object.
    """
    dsn = os.getenv("PG_DSN")

    if not dsn:
        # Try building from individual components
        user = os.getenv("PG_USER")
        password = os.getenv("PG_PASS")
        host = os.getenv("PG_HOST", "localhost")
        port = os.getenv("PG_PORT", "5432")
        database = os.getenv("PG_DB")

        if not all([user, password, database]):
            raise ValueError(
                "Database credentials not configured. "
                "Set PG_DSN or (PG_USER, PG_PASS, PG_DB) environment variables. "
                "See .env.example for reference."
            )

        dsn = f"postgresql://{user}:{password}@{host}:{port}/{database}"

    return psycopg2.connect(dsn)


# Alias for backward compatibility
get_db = get_db_connection
