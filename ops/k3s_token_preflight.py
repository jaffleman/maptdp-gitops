"""C13 : inventaire local sans valeur de token, empreinte ou clé privée affichée."""
import glob
import hmac
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys

MANAGED_TOKEN = "/etc/rancher/k3s/worker-bootstrap-token"


def read(path):
    p = pathlib.Path(path)
    return p.read_text().strip() if p.is_file() else ""


def environment(text):
    result = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"([A-Z_][A-Z0-9_]*)=(.*)", line.strip())
        if not match:
            raise ValueError("format env non pris en charge")
        value = shlex.split(match[2])
        if len(value) > 1:
            raise ValueError("valeur env ambiguë")
        result[match[1]] = value[0] if value else ""
    return result


def token_kind(value):
    value = value.strip()
    secret = value.split("::", 1)[-1]
    if re.fullmatch(r"[a-z0-9]{6}\.[a-z0-9]{16}", secret):
        return "bootstrap"
    if value.startswith("K10") and "::server:" in value:
        return "server"
    if value:
        return "static-or-unknown"
    return "absent"


def command(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=20, check=False)
        return result.returncode, result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""


def report(mode):
    unit = "k3s" if mode == "server" else "k3s-agent"
    rc, unit_text = command(["systemctl", "show", unit, "--property=ExecStart,Environment,DropInPaths,EnvironmentFiles"])
    rc_active, active = command(["systemctl", "is-active", unit])
    rc_version, version = command(["/usr/local/bin/k3s", "--version"])
    version_match = re.search(r"k3s version (v[0-9]+\.[0-9]+\.[0-9]+\+k3s[0-9]+)", version)
    config = read("/etc/rancher/k3s/config.yaml")
    token_config = bool(re.search(r"^\s*(token|agent-token)\s*:", config, re.M))
    other_config = bool(glob.glob("/etc/rancher/k3s/config.yaml.d/*.yaml"))
    known_env = "/etc/systemd/system/" + unit + ".service.env"
    env = environment(read(known_env))
    extra_env_paths = ["/etc/default/" + unit, "/etc/sysconfig/" + unit]
    # Les fichiers alternatifs sont signalés sans en afficher le contenu.
    alternate_env = any(read(path) for path in extra_env_paths)
    override = bool(re.search(r"^DropInPaths=\S", unit_text, re.M))
    cli_credentials = bool(re.search(r"--(?:token|agent-token|token-file|agent-token-file)(?:=|\s)", unit_text))
    cli_custom = bool(re.search(r"--(?:config|data-dir)(?:=|\s)", unit_text))
    cli_override = bool(re.search(r"--(?:server|node-name|datastore-endpoint)(?:=|\s)|(?:\s|^)-(?:t|s|c)(?:=|\s)", unit_text))
    env_files_line = next((line for line in unit_text.splitlines() if line.startswith('EnvironmentFiles=')), '')
    env_paths = re.findall(r'/[^\s;()]+', env_files_line)
    extra_environment_file = any(path not in [known_env] + extra_env_paths for path in env_paths)
    service_inline_credentials = bool(re.search(r"^Environment=.*K3S_(?:TOKEN|AGENT_TOKEN|TOKEN_FILE|CONFIG_FILE|DATA_DIR|DATASTORE_ENDPOINT)=", unit_text, re.M))
    config_file_match = re.search(r"^token-file:\s*[\"']?([^\s\"']+)", config, re.M)
    token_file = env.get("K3S_TOKEN_FILE") or (config_file_match[1] if config_file_match else "")
    value = env.get("K3S_TOKEN", "")
    if not value and token_file:
        # Seul le chemin géré est lu côté worker ; aucune résolution arbitraire.
        value = read(token_file) if token_file == MANAGED_TOKEN else ""
    base_config_simple = all(not line.strip() or line.lstrip().startswith("#") or re.match(
        r"^(node-ip|flannel-iface|server|node-name|token-file):\s*\S+\s*$", line) for line in config.splitlines())
    safe = rc == 0 and not any([override, cli_credentials, cli_custom, cli_override, extra_environment_file, service_inline_credentials,
                               alternate_env, other_config, token_config, env.get("K3S_CONFIG_FILE"),
                               env.get("K3S_DATA_DIR")])
    if mode == "worker":
        safe = safe and base_config_simple and token_file in ("", MANAGED_TOKEN)
    else:
        safe = safe and not config_file_match and not re.search(r'^agent-token-file:', config, re.M)
    output = {
        "mode": mode, "service_active": rc_active == 0 and active == "active",
        "version": version_match[1] if rc_version == 0 and version_match else "unknown",
        "default_layout_supported": bool(safe), "systemd_dropins": override,
        "cli_credential_options": cli_credentials, "custom_config_or_datadir": cli_custom,
        "cli_identity_or_datastore_override": cli_override, "unknown_environment_file": extra_environment_file,
        "inline_environment_credentials": service_inline_credentials,
        "alternate_env_nonempty": bool(alternate_env), "config_dropins": other_config,
        "inline_yaml_credentials": token_config,
        "env_has_literal_token": bool(env.get("K3S_TOKEN")),
        "managed_token_file_selected": token_file == MANAGED_TOKEN,
        "worker_credential_kind": token_kind(value) if mode == "worker" else "not-applicable",
    }
    if mode == "server":
        server = read("/var/lib/rancher/k3s/server/token")
        agent = read("/var/lib/rancher/k3s/server/agent-token")
        output.update({"server_token_present": bool(server),
                       "agent_token_equals_server": bool(server and agent and hmac.compare_digest(server, agent)),
                       "sqlite_present": os.path.isfile("/var/lib/rancher/k3s/server/db/state.db"),
                       "etcd_present": os.path.isdir("/var/lib/rancher/k3s/server/db/etcd"),
                       "server_env_has_fixed_token": bool(env.get("K3S_TOKEN") or env.get("K3S_TOKEN_FILE")),
                       "server_config_has_fixed_token": bool(token_config or config_file_match or re.search(r'^agent-token-file:', config, re.M)),
                       "datastore_configured": bool(env.get("K3S_DATASTORE_ENDPOINT") or re.search(r"^datastore-endpoint:", config, re.M))})
    else:
        cert = "/var/lib/rancher/k3s/agent/client-kubelet.crt"
        cert_rc, _ = command(["openssl", "x509", "-noout", "-checkend", "0", "-in", cert])
        output.update({"node_password_present": bool(read("/etc/rancher/node/password")),
                       "client_certificate_present": os.path.isfile(cert),
                       "client_certificate_unexpired": cert_rc == 0,
                       "client_key_present": os.path.isfile("/var/lib/rancher/k3s/agent/client-kubelet.key")})
    return output


if __name__ == "__main__":
    try:
        mode = json.load(sys.stdin)["mode"]
        if mode not in ("worker", "server"):
            raise ValueError("mode invalide")
        print(json.dumps(report(mode), sort_keys=True))
    except Exception:
        print('{"preflight_error": "inspection impossible ; aucune valeur confidentielle affichée"}')
        sys.exit(1)
