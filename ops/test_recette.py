"""Tests hors cluster : succès, ressources absentes et états trompeurs."""
import copy
import datetime as dt
import unittest
from unittest.mock import patch

from recette import Recipe, condition


class RecipeTests(unittest.TestCase):
    def setUp(self):
        self.recipe = Recipe({"namespace": "maptdp-staging", "expected_nodes": ["vps-cp", "vps-worker"],
                              "min_argocd_apps": 1, "min_vso_secrets": 1, "min_app_replicas": 2,
                              "backup_cronjob": "postgres-backup-cronjob", "backup_max_age_hours": 30,
                              "https_checks": [], "timeout_seconds": 1, "kubeconfig": "/fake"})

    def test_condition_rejects_stale_generation_and_missing_condition(self):
        obj = {"metadata": {"generation": 2}, "status": {"conditions": [
            {"type": "Ready", "status": "True", "observedGeneration": 1}]}}
        self.assertFalse(condition(obj, "Ready"))
        self.assertFalse(condition(obj, "Healthy"))
        obj["status"]["conditions"][0]["observedGeneration"] = 2
        self.assertTrue(condition(obj, "Ready"))

    def test_missing_expected_worker_fails(self):
        with patch.object(self.recipe, "get", return_value=[]):
            with self.assertRaisesRegex(ValueError, "nœud absent"):
                self.recipe.nodes()

    def test_empty_argocd_is_not_success(self):
        with patch.object(self.recipe, "get", return_value=[]):
            with self.assertRaises(ValueError):
                self.recipe.argocd()

    def test_backup_requires_fresh_success_owned_by_cron_uid(self):
        now = dt.datetime.now(dt.timezone.utc)
        cron = {"metadata": {"uid": "cron1", "name": "postgres-backup-cronjob"},
                "spec": {"schedule": "0 1 * * *"}}
        job = {"metadata": {"name": "dump", "creationTimestamp": now.isoformat(),
                            "ownerReferences": [{"kind": "CronJob", "uid": "cron1"}]},
               "status": {"completionTime": now.isoformat(),
                          "conditions": [{"type": "Complete", "status": "True"}]}}
        data = {"cronjobs.batch": [cron], "jobs.batch": [job]}
        with patch.object(self.recipe, "get", side_effect=lambda resource, ns: data[resource]):
            self.assertIn("S3 non vérifié", self.recipe.backup())
            job["status"]["completionTime"] = (now - dt.timedelta(hours=31)).isoformat()
            with self.assertRaisesRegex(ValueError, "hors fenêtre"):
                self.recipe.backup()
            job["metadata"]["ownerReferences"][0]["uid"] = "other-cron"
            with self.assertRaisesRegex(ValueError, "aucun Job réussi"):
                self.recipe.backup()

    def test_vso_missing_sync_is_not_healthy_success(self):
        pod = {"metadata": {"name": "vault-secrets-operator-controller"},
               "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}]}}
        secret = {"metadata": {"name": "vss", "generation": 1}, "status": {"conditions": [
            {"type": "Healthy", "status": "True"}, {"type": "Ready", "status": "True"}]}}
        with patch.object(self.recipe, "get", side_effect=lambda resource: [pod] if resource == "pods" else [secret]):
            with self.assertRaisesRegex(ValueError, "SecretSynced"):
                self.recipe.vso()
            secret["status"]["conditions"].append({"type": "SecretSynced", "status": "True"})
            self.assertIn("VaultStaticSecrets", self.recipe.vso())

    def test_workloads_require_updated_replicas(self):
        obj = {"metadata": {"name": "maptdp-frontend", "generation": 2}, "spec": {"replicas": 2},
               "status": {"observedGeneration": 2, "readyReplicas": 2, "updatedReplicas": 2}}
        backend, db = copy.deepcopy(obj), copy.deepcopy(obj)
        backend["metadata"]["name"] = "maptdp-backend"
        db["metadata"]["name"] = "maptdp-db"
        with patch.object(self.recipe, "get", side_effect=lambda resource, ns:
                          [obj, backend] if resource == "deployments.apps" else [db]):
            self.recipe.workloads()
            backend["status"]["updatedReplicas"] = 1
            with self.assertRaisesRegex(ValueError, "non actualisés"):
                self.recipe.workloads()

    def test_empty_https_checks_fails_instead_of_skipping(self):
        with self.assertRaises(ValueError):
            self.recipe.https()

    def test_http_instead_of_https_is_rejected_before_request(self):
        self.recipe.c["https_checks"] = [{"url": "http://example.com"}]
        with self.assertRaises(ValueError):
            self.recipe.https()

    def test_kubectl_reads_only_and_hides_raw_error_output(self):
        class Result:
            returncode = 0
            stdout = '{"items": []}'
        with patch("recette.subprocess.run", return_value=Result()) as call:
            self.assertEqual(self.recipe.get("nodes"), [])
            args, options = call.call_args
            self.assertIn("get", args[0])
            self.assertNotIn("shell", options)
            self.assertLessEqual(options["timeout"], 30)
        Result.returncode = 1
        Result.stdout = "sensitive-response"
        with patch("recette.subprocess.run", return_value=Result()):
            with self.assertRaisesRegex(ValueError, "lecture kubectl") as error:
                self.recipe.get("nodes")
            self.assertNotIn("sensitive", str(error.exception))


if __name__ == "__main__":
    unittest.main()
