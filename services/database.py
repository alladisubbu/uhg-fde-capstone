import json
import os
from contextlib import contextmanager

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]


@contextmanager
def get_connection():
    connection = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def fetch_one(query: str, parameters: tuple = ()):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, parameters)
            return cursor.fetchone()


def fetch_all(query: str, parameters: tuple = ()):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, parameters)
            return cursor.fetchall()


def execute(query: str, parameters: tuple = ()):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, parameters)
            try:
                return cursor.fetchone()
            except psycopg.ProgrammingError:
                return None


def write_audit(
    case_id: str | None,
    actor: str,
    action: str,
    before_state=None,
    after_state=None,
    metadata=None,
):
    execute(
        """
        INSERT INTO audit_log(
            case_id, actor, action, before_state, after_state, metadata
        )
        VALUES (
            %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb
        )
        """,
        (
            case_id,
            actor,
            action,
            json.dumps(before_state) if before_state is not None else None,
            json.dumps(after_state) if after_state is not None else None,
            json.dumps(metadata or {}),
        ),
    )
