import os
from contextlib import contextmanager

from dotenv import load_dotenv
from langgraph.checkpoint.postgres import PostgresSaver

from graph.claims_graph import build_graph

load_dotenv()


@contextmanager
def get_postgres_graph():
    connection_string = os.environ["DATABASE_URL"]

    with PostgresSaver.from_conn_string(connection_string) as checkpointer:
        checkpointer.setup()
        graph = build_graph(checkpointer=checkpointer)
        yield graph
