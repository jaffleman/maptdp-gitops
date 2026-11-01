"""C13 : prouver Ready ET un renouvellement de Lease après le redémarrage."""
import datetime as dt
import json
import subprocess
import sys


def renewed(node, lease, since):
    ready = any(c.get("type") == "Ready" and c.get("status") == "True"
                for c in node.get("status", {}).get("conditions", []))
    value = lease.get("spec", {}).get("renewTime")
    return bool(ready and value and dt.datetime.fromisoformat(value.replace("Z", "+00:00")) >
                dt.datetime.fromisoformat(since.replace("Z", "+00:00")))


if __name__ == "__main__":
    try:
        config = json.load(sys.stdin)
        base = ["/usr/local/bin/k3s", "kubectl", "--kubeconfig", "/etc/rancher/k3s/k3s.yaml", "--request-timeout=10s", "get"]
        node = json.loads(subprocess.run(base + ["node", config["node"], "-o", "json"],
                                        check=True, capture_output=True, text=True, timeout=15).stdout)
        lease = json.loads(subprocess.run(base + ["lease", config["node"], "-n", "kube-node-lease", "-o", "json"],
                                         check=True, capture_output=True, text=True, timeout=15).stdout)
        ok = renewed(node, lease, config["since"])
        print("Ready et Lease renouvelé après redémarrage" if ok else "En attente du nouveau Lease/Ready")
        sys.exit(0 if ok else 1)
    except Exception:
        print("Lecture Node/Lease impossible ; aucun identifiant affiché")
        sys.exit(1)
