# =====================================================================
# Lot 2 — Panier et Sessions (Redis) : connexion et mesure de latence
# Usage : python lot2-panier-redis/client_redis.py
# =====================================================================

import sys
import time

import redis

sys.stdout.reconfigure(encoding="utf-8")


def get_client():
    """Client Redis partagé par les scripts du Lot 2."""
    # decode_responses=True : Redis renvoie des str au lieu de bytes
    return redis.Redis(host="localhost", port=6379, decode_responses=True)


if __name__ == "__main__":
    r = get_client()

    print("Connexion :", "OK" if r.ping() else "échec")
    print("Version de Redis :", r.info("server")["redis_version"])

    # Latence moyenne sur 1 000 écritures et 1 000 lectures
    N = 1000
    debut = time.perf_counter()
    for i in range(N):
        r.set(f"test:latence:{i}", "valeur")
    duree_ecriture = (time.perf_counter() - debut) / N

    debut = time.perf_counter()
    for i in range(N):
        r.get(f"test:latence:{i}")
    duree_lecture = (time.perf_counter() - debut) / N

    print(f"Latence moyenne SET : {duree_ecriture * 1000:.3f} ms")
    print(f"Latence moyenne GET : {duree_lecture * 1000:.3f} ms")

    r.delete(*[f"test:latence:{i}" for i in range(N)])   # nettoyage