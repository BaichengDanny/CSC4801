"""Context-scoped SQLite connections and explicit write transactions."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import click
from flask import current_app, g

from .errors import DomainError


def get_db():
    if 'db' not in g:
        path = current_app.config['DATABASE']
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(path, timeout=10, isolation_level=None)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db


def close_db(exception=None):
    connection = g.pop('db', None)
    if connection is not None:
        connection.close()


@contextmanager
def transaction():
    connection = get_db()
    nested = connection.in_transaction
    try:
        if nested:
            connection.execute('SAVEPOINT service_write')
        else:
            connection.execute('BEGIN IMMEDIATE')
        yield connection
        if nested:
            connection.execute('RELEASE SAVEPOINT service_write')
        else:
            connection.commit()
    except Exception as error:
        if nested:
            connection.execute('ROLLBACK TO SAVEPOINT service_write')
            connection.execute('RELEASE SAVEPOINT service_write')
        else:
            connection.rollback()
        if isinstance(error, sqlite3.OperationalError) and getattr(error, 'sqlite_errorcode', None) in (
                sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
            raise DomainError(503, 'Database is busy. Please try again.') from error
        raise


def migrate():
    connection = get_db()
    connection.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY)')
    for migration in sorted(Path(__file__).with_name('migrations').glob('*.sql')):
        if connection.execute('SELECT 1 FROM schema_migrations WHERE version = ?', (migration.name,)).fetchone():
            continue
        try:
            # Migration contents are trusted, version-controlled SQL, never request input.
            connection.executescript('BEGIN IMMEDIATE;\n' + migration.read_text(encoding='utf-8'))
            connection.execute('INSERT INTO schema_migrations VALUES (?)', (migration.name,))
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def init_app(app):
    app.teardown_appcontext(close_db)

    @app.cli.command('init-db')
    def init_db_command():
        """Apply pending database migrations without resetting data."""
        migrate()
        click.echo('Database migrations applied.')
