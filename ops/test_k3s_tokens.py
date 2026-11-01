"""C13 : tests de confidentialité, de refus des surcharges et de réenrôlement."""
import json
import unittest
from unittest.mock import patch

import k3s_token_preflight as preflight
from k3s_node_rejoined import renewed


class TokenPreflightTests(unittest.TestCase):
    def setUp(self):
        # Valeurs synthétiques de test, aucun identifiant réel.
        self.fake = "K10" + "0" * 64 + "::server:SYNTHETIC-NOT-A-REAL-SECRET"
        self.files = {
            "/etc/systemd/system/k3s-agent.service.env": "K3S_TOKEN='" + self.fake + "'\nK3S_URL='https://cp:6443'",
            "/etc/rancher/k3s/config.yaml": "node-ip: 100.64.0.2\nflannel-iface: tailscale0",
            "/etc/rancher/node/password": "SYNTHETIC-PASSWORD",
            "/var/lib/rancher/k3s/server/token": self.fake,
            "/var/lib/rancher/k3s/server/agent-token": self.fake,
        }
        self.unit = "ExecStart={ path=/usr/local/bin/k3s ; argv[]=/usr/local/bin/k3s agent ; }\nEnvironment=\nDropInPaths=\nEnvironmentFiles=/etc/systemd/system/k3s-agent.service.env (ignore_errors=yes)"

    def run_report(self, mode="worker"):
        def command(args):
            if args[:2] == ["systemctl", "show"]:
                return 0, self.unit
            if args[0] == "systemctl":
                return 0, "active"
            if args[0] == "/usr/local/bin/k3s":
                return 0, "k3s version v1.36.5+k3s1 (synthetic)"
            return 0, ""
        with patch.object(preflight, "read", side_effect=lambda path: self.files.get(path, "")), \
             patch.object(preflight, "command", side_effect=command), \
             patch.object(preflight.glob, "glob", return_value=[]), \
             patch.object(preflight.os.path, "isfile", return_value=True), \
             patch.object(preflight.os.path, "isdir", return_value=False):
            return preflight.report(mode)

    def test_report_does_not_disclose_token_password_or_fingerprint(self):
        result = self.run_report()
        self.assertTrue(result["default_layout_supported"])
        self.assertTrue(result["env_has_literal_token"])
        self.assertEqual(result["worker_credential_kind"], "server")
        text = json.dumps(result)
        self.assertNotIn(self.fake, text)
        self.assertNotIn("SYNTHETIC-PASSWORD", text)
        self.assertNotIn("0" * 64, text)

    def test_static_unknown_is_not_mistaken_for_bootstrap(self):
        self.assertEqual(preflight.token_kind("arbitrary-static"), "static-or-unknown")
        self.assertEqual(preflight.token_kind("K10" + "0" * 64 + "::abcdef." + "a" * 16), "bootstrap")

    def test_env_is_parsed_without_shell_evaluation(self):
        result = preflight.environment("K3S_TOKEN='$(do-not-run)'\n# ignored\nEMPTY=")
        self.assertEqual(result["K3S_TOKEN"], "$(do-not-run)")
        self.assertEqual(result["EMPTY"], "")

    def test_unknown_env_syntax_is_refused_without_including_value(self):
        with self.assertRaises(ValueError) as error:
            preflight.environment("export K3S_TOKEN='SYNTHETIC'")
        self.assertNotIn("SYNTHETIC", str(error.exception))

    def test_systemd_dropin_and_extra_env_file_refuse_migration(self):
        self.unit += "\nDropInPaths=/etc/systemd/system/k3s-agent.service.d/custom.conf"
        self.assertFalse(self.run_report()["default_layout_supported"])
        self.unit = "ExecStart=agent\nEnvironmentFiles=/custom/credentials"
        result = self.run_report()
        self.assertTrue(result["unknown_environment_file"])
        self.assertFalse(result["default_layout_supported"])

    def test_command_line_credentials_or_identity_overrides_refuse_migration(self):
        for flag in ["--token", "--token-file", "--config", "--server", "-t"]:
            self.unit = "ExecStart=/usr/local/bin/k3s agent " + flag + " hidden\nEnvironment=\nDropInPaths="
            self.assertFalse(self.run_report()["default_layout_supported"], flag)

    def test_unmanaged_yaml_keys_or_token_file_refuse_worker_migration(self):
        for line in ["token: hidden", "token-file: /other/path", "kubelet-arg: something"]:
            self.files["/etc/rancher/k3s/config.yaml"] = line
            self.assertFalse(self.run_report()["default_layout_supported"], line)

    def test_managed_bootstrap_is_reported_without_value(self):
        bootstrap = "K10" + "0" * 64 + "::abcdef." + "a" * 16
        self.files["/etc/systemd/system/k3s-agent.service.env"] = "K3S_TOKEN_FILE='" + preflight.MANAGED_TOKEN + "'"
        self.files[preflight.MANAGED_TOKEN] = bootstrap
        result = self.run_report()
        self.assertTrue(result["managed_token_file_selected"])
        self.assertEqual(result["worker_credential_kind"], "bootstrap")
        self.assertNotIn(bootstrap, json.dumps(result))

    def test_server_reports_equality_without_exporting_credential(self):
        self.unit = "ExecStart=/usr/local/bin/k3s server\nEnvironment=\nDropInPaths="
        result = self.run_report("server")
        self.assertTrue(result["agent_token_equals_server"])
        self.assertTrue(result["server_token_present"])
        self.assertNotIn(self.fake, json.dumps(result))


class NodeRejoinedTests(unittest.TestCase):
    def test_ready_is_insufficient_without_post_restart_lease(self):
        node = {"status": {"conditions": [{"type": "Ready", "status": "True"}]}}
        self.assertFalse(renewed(node, {}, "2026-11-01T10:00:00Z"))
        self.assertFalse(renewed(node, {"spec": {"renewTime": "2026-11-01T09:59:59Z"}}, "2026-11-01T10:00:00Z"))
        self.assertTrue(renewed(node, {"spec": {"renewTime": "2026-11-01T10:00:01.123456Z"}}, "2026-11-01T10:00:00Z"))
        node["status"]["conditions"][0]["status"] = "False"
        self.assertFalse(renewed(node, {"spec": {"renewTime": "2026-11-01T10:00:02Z"}}, "2026-11-01T10:00:00Z"))


if __name__ == "__main__":
    unittest.main()
