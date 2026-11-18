# =====================================================================
# Lot 3 — Logs et Analytics (Cassandra) : connexion et création du schéma
# Usage : python lot3-logs-cassandra/client_cassandra.py
# =====================================================================

import sys
from pathlib import Path

from cassandra.cluster import Cluster

sys.stdout.reconfigure(encoding="utf-8")

KEYSPACE = "ldlc_logs"


def get_session():
    """Session Cassandra partagée par les scripts du Lot 3."""
    return Cluster(["localhost"], port=9042).connect(KEYSPACE)


if __name__ == "__main__":
    session = Cluster(["localhost"], port=9042).connect()

    # Le driver n'exécute qu'une instruction à la fois : on découpe le fichier
    cql = (Path(__file__).parent / "schema.cql").read_text(encoding="utf-8")
    cql = "\n".join(ligne.split("--")[0] for ligne in cql.splitlines())
    for instruction in cql.split(";"):
        if instruction.strip():
            session.execute(instruction)

    print("Tables créées :")
    for t in session.execute(
            "SELECT table_name FROM system_schema.tables WHERE keyspace_name = %s", [KEYSPACE]):
        print(" -", t.table_name)
