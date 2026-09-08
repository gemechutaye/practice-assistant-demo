"""Apply versioned schema and the LangGraph checkpoint schema."""

import psycopg
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres import PostgresSaver

from .config import settings
from .store import Store


def migrate():
    config = settings()
    Store(config.database_url).migrate()
    with psycopg.connect(
        config.database_url,
        autocommit=True,
        row_factory=dict_row,
        prepare_threshold=0,
        options="-c search_path=pa_checkpoint,public",
    ) as conn:
        PostgresSaver(conn).setup()
    print("Practice Assistant database migrations complete.")


if __name__ == "__main__":
    migrate()
