"""
Script to initialize the database.
"""
import asyncio
import sys
from pathlib import Path

import click

# Ensure the project root (containing the `src` package) is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import settings
from src.db.database import init_db

@click.command()
def main():
    """Initializes the PostgreSQL database."""
    click.echo("Initializing database...")
    try:
        asyncio.run(init_db(settings))
        click.echo(click.style("Database initialized successfully.", fg="green"))
    except Exception as e:
        click.echo(click.style(f"Error during initialization: {e}", fg="red"))
        raise click.Abort()

if __name__ == "__main__":
    main()
