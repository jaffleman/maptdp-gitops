"""Saisie locale masquée d'un accès Vault pour la sauvegarde C13.

Ne crée pas de token Vault. Le token fourni est validé puis conservé en tmpfs,
mode 0600, hors dépôt. La fenêtre d'utilisation locale est limitée à 20 minutes ;
cela ne change pas le TTL réel du token Vault. Supprimer la copie après usage.
"""
import getpass
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.request

VAULT_ADDR = "http://100.91.75.58:8200"


def session_path():
    return Path("/dev/shm") / ("maptdp-c13-vault-%d.json" % os.getuid())


def save_session(token, expires_at, target):
    if target.exists() or target.is_symlink():
        info = target.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise ValueError("fichier de session existant non sûr")
    fd, temporary = tempfile.mkstemp(prefix=".maptdp-c13-", dir=target.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump({"vault_addr": VAULT_ADDR, "token": token, "expires_at": expires_at}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    if not sys.stdin.isatty():
        print("Saisie interactive requise dans ton terminal Ubuntu ; aucun token en argument ou via pipe.")
        return 1
    if not Path("/dev/shm").is_dir():
        print("tmpfs /dev/shm absent ; aucune session enregistrée.")
        return 1
    token = getpass.getpass("Token Vault autorisé à sauvegarder les secrets C13 (saisie masquée) : ").strip()
    if not token:
        print("Token vide ; aucune session enregistrée.")
        return 1
    try:
        # Aucun proxy tiers : destination tailnet connue, explicitement choisie.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        request = urllib.request.Request(VAULT_ADDR + "/v1/auth/token/lookup-self", headers={"X-Vault-Token": token})
        with opener.open(request, timeout=15) as response:
            data = json.load(response).get("data", {})
        ttl = data.get("ttl", 0)
        duration = min(1200, int(ttl)) if ttl else 1200
        if duration <= 0:
            raise ValueError("token sans durée valide")
        save_session(token, time.time() + duration, session_path())
        print("Accès Vault validé ; session locale 0600 en mémoire temporaire, au plus 20 minutes.")
        print("Aucun token affiché. La permission d'archivage sera contrôlée avant rotation.")
        return 0
    except urllib.error.HTTPError as error:
        print("Authentification Vault refusée (HTTP %d) ; aucune nouvelle session enregistrée." % error.code)
    except Exception:
        print("Validation impossible ; aucune nouvelle session enregistrée et aucun identifiant affiché.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
