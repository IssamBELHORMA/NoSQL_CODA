# =====================================================================
# Lot 2 — Sessions utilisateurs (Redis)
# Usage : python lot2-panier-redis/sessions.py
# =====================================================================

import sys
import time
import uuid
from datetime import datetime, timezone

from client_redis import get_client

sys.stdout.reconfigure(encoding="utf-8")

TTL_SESSION = 30 * 60   # 30 minutes d'inactivité


def maintenant():
    return datetime.now(timezone.utc).isoformat()


def creer_session(r, user_id="", nom="", ttl=TTL_SESSION):
    """Crée une session et renvoie son identifiant (à stocker dans le cookie)."""
    session_id = str(uuid.uuid4())
    cle = f"session:{session_id}"

    pipe = r.pipeline(transaction=True)            # MULTI ... EXEC : atomique
    pipe.hset(cle, mapping={
        "user_id": user_id,
        "nom": nom,
        "derniere_page": "/",
        "cree_le": maintenant(),
        "maj_le": maintenant(),
    })
    pipe.expire(cle, ttl)
    if user_id:
        pipe.sadd(f"user:{user_id}:sessions", session_id)
    pipe.execute()

    return session_id


def lire_session(r, session_id, page=None):
    """Lit la session à chaque requête et prolonge son TTL (TTL glissant)."""
    cle = f"session:{session_id}"
    if not r.exists(cle):
        return None                                # expirée ou inexistante

    pipe = r.pipeline(transaction=True)
    if page:
        pipe.hset(cle, mapping={"derniere_page": page, "maj_le": maintenant()})
    pipe.expire(cle, TTL_SESSION)                  # remise à 30 minutes
    pipe.hgetall(cle)
    return pipe.execute()[-1]


def supprimer_session(r, session_id):
    """Déconnexion d'un appareil."""
    cle = f"session:{session_id}"
    user_id = r.hget(cle, "user_id")
    r.delete(cle)
    if user_id:
        r.srem(f"user:{user_id}:sessions", session_id)


def deconnecter_partout(r, user_id):
    """Déconnexion de tous les appareils d'un utilisateur."""
    ids = r.smembers(f"user:{user_id}:sessions")
    if ids:
        r.delete(*[f"session:{s}" for s in ids])
    r.delete(f"user:{user_id}:sessions")
    return len(ids)


# Démonstration
if __name__ == "__main__":
    # Deux clients = deux serveurs web différents derrière le load balancer
    serveur_a = get_client()
    serveur_b = get_client()

    print("===== 1. Session partagée entre serveurs =====")
    sid = creer_session(serveur_a, user_id="U1024", nom="Alice")
    print("Créée par le serveur A :", sid)
    print("Lue par le serveur B :", lire_session(serveur_b, sid, page="/produit/amd-ryzen-7-7800x3d"))
    print("TTL restant :", serveur_b.ttl(f"session:{sid}"), "secondes")

    print("\n===== 2. Visiteur non connecté =====")
    sid_anonyme = creer_session(serveur_a)
    print("Session anonyme :", lire_session(serveur_a, sid_anonyme))

    print("\n===== 3. Expiration automatique (TTL de 3 secondes) =====")
    sid_court = creer_session(serveur_a, user_id="U2048", nom="Bob", ttl=3)
    print("Existe avant expiration :", serveur_a.exists(f"session:{sid_court}") == 1)
    time.sleep(4)
    print("Après 4 secondes :", lire_session(serveur_a, sid_court))

    print("\n===== 4. Déconnexion de tous les appareils =====")
    creer_session(serveur_a, user_id="U1024", nom="Alice")   # 2e appareil
    print("Sessions d'Alice :", serveur_a.scard("user:U1024:sessions"))
    print("Sessions supprimées :", deconnecter_partout(serveur_a, "U1024"))
    print("Session initiale encore valide :", lire_session(serveur_b, sid) is not None)

    # Nettoyage
    supprimer_session(serveur_a, sid_anonyme)
    serveur_a.delete("user:U2048:sessions")