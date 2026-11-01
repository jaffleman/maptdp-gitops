"""C11 : contrôles bornés en lecture seule. Configuration JSON sur stdin.

Ne lit aucun objet Secret ; aucun apply/patch/exec ni écriture de fichier.
Les erreurs de kubectl/HTTP sont résumées sans reproduire les réponses brutes.
"""
import datetime as dt
import json
import subprocess
import sys
import urllib.parse
import urllib.request


def require(ok, message):
    if not ok:
        raise ValueError(message)


def timestamp(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def condition(obj, *types):
    found = {c["type"]: c for c in obj.get("status", {}).get("conditions", [])}
    generation = obj.get("metadata", {}).get("generation")
    for kind in types:
        c = found.get(kind)
        if c and c.get("status") == "True":
            # Certains CRD n'exposent pas observedGeneration sur leurs conditions.
            if generation is None or c.get("observedGeneration", generation) == generation:
                return True
    return False


def identity(obj):
    meta = obj.get("metadata", {})
    return "/".join(filter(None, [meta.get("namespace"), meta.get("name")]))


class Recipe:
    def __init__(self, config):
        self.c = config
        self.failures = 0

    def get(self, resource, namespace=None):
        args = ["kubectl", "--kubeconfig", self.c["kubeconfig"],
                "--request-timeout=" + str(self.c["timeout_seconds"]) + "s", "get", resource]
        args += ["-n", namespace] if namespace else ["-A"]
        args += ["-o", "json"]
        try:
            result = subprocess.run(args, capture_output=True, text=True,
                                    timeout=self.c["timeout_seconds"] + 5, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise ValueError("kubectl indisponible ou délai dépassé : " + resource) from None
        require(result.returncode == 0, "lecture kubectl refusée/échouée : " + resource)
        try:
            return json.loads(result.stdout)["items"]
        except (ValueError, KeyError, TypeError):
            raise ValueError("réponse JSON inexploitable : " + resource) from None

    def run_check(self, name, fn):
        try:
            detail = fn()
            print("OK | " + name + " | " + detail)
        except (ValueError, KeyError, TypeError) as exc:
            self.failures += 1
            print("ECHEC | " + name + " | " + str(exc))

    def nodes(self):
        nodes = self.get("nodes")
        by_name = {n["metadata"]["name"]: n for n in nodes}
        require(bool(self.c["expected_nodes"]), "liste des nœuds attendus vide")
        for name in self.c["expected_nodes"]:
            require(name in by_name, "nœud absent : " + name)
        for node in nodes:
            require(condition(node, "Ready"), "nœud non Ready : " + identity(node))
            require(not node.get("spec", {}).get("unschedulable", False),
                    "nœud cordonné : " + identity(node))
        versions = {n["status"]["nodeInfo"]["kubeletVersion"] for n in nodes}
        require(len(versions) == 1, "versions kubelet différentes : " + ", ".join(sorted(versions)))
        return str(len(nodes)) + " nœuds Ready ; version " + next(iter(versions))

    def argocd(self):
        apps = self.get("applications.argoproj.io", "argocd")
        require(len(apps) >= self.c["min_argocd_apps"], "nombre d'applications inférieur au minimum")
        for app in apps:
            status = app.get("status", {})
            require(status.get("sync", {}).get("status") == "Synced" and
                    status.get("health", {}).get("status") == "Healthy",
                    "application non Synced/Healthy : " + identity(app))
            require(status.get("operationState", {}).get("phase") not in
                    ("Running", "Terminating", "Failed", "Error"),
                    "opération ArgoCD non terminée ou échouée : " + identity(app))
        return str(len(apps)) + " applications Synced/Healthy"

    def vso(self):
        pods = [p for p in self.get("pods") if
                "vault-secrets-operator" in p["metadata"]["name"] and
                not p["metadata"].get("deletionTimestamp")]
        require(bool(pods), "aucun pod vault-secrets-operator trouvé")
        for pod in pods:
            require(pod.get("status", {}).get("phase") == "Running" and condition(pod, "Ready"),
                    "pod VSO non Running/Ready : " + identity(pod))
        secrets = self.get("vaultstaticsecrets.secrets.hashicorp.com")
        require(len(secrets) >= self.c["min_vso_secrets"], "nombre de VaultStaticSecrets insuffisant")
        for secret in secrets:
            for aliases in [("SecretSynced", "Synced"), ("Healthy",), ("Ready",)]:
                require(condition(secret, *aliases),
                        "condition " + "/".join(aliases) + " absente/fausse/périmée : " + identity(secret))
        return str(len(secrets)) + " VaultStaticSecrets Synced/Healthy/Ready (états déclarés)"

    def backup(self):
        ns = self.c["namespace"]
        crons = self.get("cronjobs.batch", ns)
        cron = next((c for c in crons if c["metadata"]["name"] == self.c["backup_cronjob"]), None)
        require(cron is not None, "CronJob absent")
        require(not cron["spec"].get("suspend", False), "CronJob suspendu")
        require(bool(cron["spec"].get("schedule")), "planification absente")
        uid = cron["metadata"]["uid"]
        jobs = [j for j in self.get("jobs.batch", ns) if any(
            r.get("uid") == uid and r.get("kind") == "CronJob"
            for r in j["metadata"].get("ownerReferences", []))]
        successes = [j for j in jobs if condition(j, "Complete") and j.get("status", {}).get("completionTime")]
        require(bool(successes), "aucun Job réussi appartenant au CronJob dans l'historique conservé")
        latest = max(successes, key=lambda j: timestamp(j["status"]["completionTime"]))
        age = (dt.datetime.now(dt.timezone.utc) - timestamp(latest["status"]["completionTime"])).total_seconds() / 3600
        require(0 <= age <= self.c["backup_max_age_hours"], "dernier succès hors fenêtre : %.1f h" % age)
        newest = max(jobs, key=lambda j: timestamp(j["metadata"]["creationTimestamp"]))
        require(not condition(newest, "Failed"), "dernier Job planifié échoué : " + identity(newest))
        if not condition(newest, "Complete"):
            running_age = (dt.datetime.now(dt.timezone.utc) - timestamp(newest["metadata"]["creationTimestamp"])).total_seconds()
            require(running_age <= 3600, "dernier Job non terminé depuis plus d'une heure")
        return identity(latest) + " réussi il y a %.1f h ; S3 non vérifié" % age

    def workloads(self):
        ns = self.c["namespace"]
        deployments = self.get("deployments.apps", ns)
        statefulsets = self.get("statefulsets.apps", ns)
        for component in ["frontend", "backend"]:
            matches = [d for d in deployments if component in d["metadata"]["name"]]
            require(bool(matches), "Deployment " + component + " absent")
            require(all(d.get("spec", {}).get("replicas", 1) >= self.c["min_app_replicas"] for d in matches),
                    "réplicas souhaités insuffisants pour " + component)
        require(any("maptdp-db" in s["metadata"]["name"] for s in statefulsets), "StatefulSet maptdp-db absent")
        for obj in deployments + statefulsets:
            desired = obj.get("spec", {}).get("replicas", 1)
            status = obj.get("status", {})
            require(desired > 0, "workload à zéro : " + identity(obj))
            require(status.get("observedGeneration", 0) >= obj["metadata"].get("generation", 1),
                    "génération non observée : " + identity(obj))
            require(status.get("readyReplicas", 0) == desired and status.get("updatedReplicas", 0) == desired,
                    "réplicas non prêts ou non actualisés : " + identity(obj))
        return str(len(deployments)) + " Deployments et " + str(len(statefulsets)) + " StatefulSets prêts/actualisés"

    def https(self):
        checks = self.c["https_checks"]
        require(bool(checks), "recette_https_checks vide : fournir les URLs HTTPS et codes attendus")
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        opener = urllib.request.build_opener(NoRedirect())
        for check in checks:
            parsed = urllib.parse.urlsplit(check["url"])
            require(parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password,
                    "URL HTTPS invalide ou contenant des identifiants")
            try:
                with opener.open(check["url"], timeout=self.c["timeout_seconds"]) as response:
                    require(response.status == check.get("status", 200), "code HTTP inattendu")
            except ValueError:
                raise
            except Exception:
                raise ValueError("échec HTTPS (TLS/DNS/réseau/code/redirection) pour " + parsed.hostname) from None
        return str(len(checks)) + " réponses HTTPS conformes ; certificats vérifiés ; aucun parcours métier"

    def run(self):
        for name, fn in [("Nœuds", self.nodes), ("ArgoCD", self.argocd),
                         ("VSO", self.vso), ("Cron dump", self.backup),
                         ("Application - workloads", self.workloads), ("Application - HTTPS", self.https)]:
            self.run_check(name, fn)
        print("BILAN | %d contrôle(s) en échec ; aucune modification du cluster" % self.failures)
        return int(self.failures != 0)


if __name__ == "__main__":
    sys.exit(Recipe(json.load(sys.stdin)).run())
