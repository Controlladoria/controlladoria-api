"""
Create database if it doesn't exist
Run this before migrations in production
"""

import os
import sys

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy.engine.url import make_url


def create_database_if_not_exists():
    """Create the database if it doesn't exist"""
    database_url = os.getenv("DATABASE_URL")

    if not database_url or database_url.startswith("sqlite"):
        print("SQLite database - no creation needed")
        return

    # Parse DATABASE_URL using SQLAlchemy's URL parser (handles special chars in passwords)
    try:
        url = make_url(database_url)
        username = url.username
        password = url.password
        hostname = url.host
        port = url.port or 5432
        database = url.database

        print(f"Checking if database '{database}' exists on {hostname}...")

        # Connect to 'postgres' database to create our target database
        conn = psycopg2.connect(
            dbname="postgres",
            user=username,
            password=password,
            host=hostname,
            port=port,
            connect_timeout=10,
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

        cursor = conn.cursor()

        # Check if database exists
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (database,),
        )
        exists = cursor.fetchone()

        if not exists:
            print(f"Creating database '{database}'...")
            cursor.execute(f'CREATE DATABASE "{database}"')
            print(f"Database '{database}' created successfully!")
        else:
            print(f"Database '{database}' already exists.")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"Error creating database: {e}")
        sys.exit(1)


if __name__ == "__main__":
    create_database_if_not_exists()
