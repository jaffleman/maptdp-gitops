"""C14 : inspecter SSH/UFW localement et vérifier une connexion SSH neuve.

Lecture seule. Les probes réseau n'envoient aucun identifiant aux IP publiques
découvertes ; seule la cible d'inventaire reçoit une connexion authentifiée.
"""
import errno
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys


def run(args, timeout=20):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                                env=dict(os.environ, LC_ALL='C'), check=False)
        return result.returncode, result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return 127, ''


def listening_ports(text):
    ports = set()
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 4 and fields[0] == 'LISTEN':
            value = fields[3].rsplit(':', 1)[-1]
            if value.isdigit():
                ports.add(int(value))
    return ports


def firewall_posture(text, ipv6_enabled):
    text = '\n'.join(line.split('#', 1)[0].rstrip() for line in text.splitlines())
    # Le filet 22 explicite doit avoir disparu, même si un deny coexiste.
    allow22 = bool(re.search(r'^22(?:/tcp)?(?:\s+\(v6\))?\s+(?:ALLOW|LIMIT)', text, re.M))
    deny4 = bool(re.search(r'^22(?:/tcp)?\s+DENY\s+IN\s+Anywhere\s*$', text, re.M))
    deny6 = bool(re.search(r'^22(?:/tcp)?\s+\(v6\)\s+DENY\s+IN\s+Anywhere\s+\(v6\)\s*$', text, re.M))
    return {'active': 'Status: active' in text,
            'incoming_default_deny': bool(re.search(r'Default:\s*deny\s*\(incoming\)', text)),
            'explicit_allow22': allow22, 'deny22_ipv4': deny4,
            'deny22_ipv6': deny6, 'ipv6_enabled': ipv6_enabled}


def local_failures(report, port):
    errors = []
    if not report['sshd_syntax_valid']:
        errors.append('configuration sshd invalide')
    if report['configured_ports'] != [port]:
        errors.append('ports effectifs sshd différents du port attendu')
    if report['configured_listener_ports'] != [port]:
        errors.append('ListenAddress effectif ne correspond pas au port attendu')
    if report['listen22']:
        errors.append('écoute TCP sur le port 22 encore présente')
    if not report['listen_target']:
        errors.append('aucune écoute TCP sur le nouveau port')
    if not (report['ssh_service_active'] and report['ssh_service_enabled']):
        errors.append('ssh.service doit être actif et activé au boot')
    if not report['ssh_socket_inactive_disabled']:
        errors.append('ssh.socket doit être inactif et désactivé/masqué')
    firewall = report['firewall']
    if not firewall['active'] or not firewall['incoming_default_deny']:
        errors.append('UFW inactif ou politique entrante non deny')
    if firewall['explicit_allow22'] or not firewall['deny22_ipv4']:
        errors.append('posture UFW IPv4 du port 22 non conforme')
    if firewall['ipv6_enabled'] and not firewall['deny22_ipv6']:
        errors.append('deny UFW IPv6 du port 22 absent')
    return errors


def inspect(port):
    syntax, _ = run(['/usr/sbin/sshd', '-t'])
    effective_rc, effective = run(['/usr/sbin/sshd', '-T'])
    ss_rc, sockets = run(['ss', '-H', '-ltn'])
    fw_rc, firewall = run(['ufw', 'status', 'verbose'])
    active_rc, active = run(['systemctl', 'is-active', 'ssh.service'])
    enabled_rc, enabled = run(['systemctl', 'is-enabled', 'ssh.service'])
    _, socket_active = run(['systemctl', 'is-active', 'ssh.socket'])
    _, socket_enabled = run(['systemctl', 'is-enabled', 'ssh.socket'])
    if ss_rc or fw_rc or effective_rc:
        raise ValueError('inspection ss/ufw/sshd impossible')
    ports = listening_ports(sockets)
    v6 = bool(re.search(r'^IPV6\s*=\s*["\']?yes', Path('/etc/default/ufw').read_text(), re.M))
    report = {
        'sshd_syntax_valid': syntax == 0,
        'configured_ports': sorted(set(int(p) for p in re.findall(r'^port\s+(\d+)$', effective, re.M))),
        'configured_listener_ports': sorted(set(int(endpoint.rsplit(':', 1)[-1])
            for endpoint in re.findall(r'^listenaddress\s+(\S+)$', effective, re.M)
            if endpoint.rsplit(':', 1)[-1].isdigit())),
        'listen22': 22 in ports, 'listen_target': port in ports,
        'ssh_service_active': active_rc == 0 and active == 'active',
        'ssh_service_enabled': enabled_rc == 0 and enabled == 'enabled',
        'ssh_socket_inactive_disabled': socket_active == 'inactive' and socket_enabled in ('disabled', 'masked'),
        'firewall': firewall_posture(firewall, v6),
    }
    ip_rc, addresses = run(['ip', '-j', 'address', 'show', 'scope', 'global'])
    if ip_rc:
        raise ValueError('inventaire des adresses impossible')
    public = []
    for interface in json.loads(addresses):
        for address in interface.get('addr_info', []):
            value = address.get('local', '')
            if value and ipaddress.ip_address(value).is_global:
                public.append(value)
    report['public_addresses'] = sorted(set(public))
    report['failures'] = local_failures(report, port)
    return report


def probe(host, port):
    try:
        with socket.create_connection((host, port), timeout=3):
            return 'open'
    except ConnectionRefusedError:
        return 'refused'
    except (TimeoutError, socket.timeout):
        return 'timeout'
    except OSError as error:
        if error.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH, errno.EADDRNOTAVAIL):
            return 'unreachable'
        return 'error'


def controller(config):
    host, port, user = config['host'], int(config['port']), config['user']
    errors, warnings, probes = [], [], []
    args = ['ssh', '-i', str(Path(config['identity_file']).expanduser()), '-p', str(port),
            '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'ControlMaster=no', '-o', 'ControlPath=none', '-o', 'IdentitiesOnly=yes',
            '-o', 'PasswordAuthentication=no', '-o', 'KbdInteractiveAuthentication=no',
            '-o', 'PreferredAuthentications=publickey',
            '-o', 'ConnectTimeout=10', user + '@' + host, '/usr/bin/id -un']
    rc, identity = run(args)
    fresh = rc == 0 and identity == user
    if not fresh:
        errors.append('nouvelle connexion SSH par clé sur le port cible non validée')
    for endpoint in dict.fromkeys([host] + config['public_addresses']):
        legacy = probe(endpoint, 22)
        probes.append({'host': endpoint, 'port22': legacy})
        if legacy == 'open':
            errors.append('port 22 accessible sur ' + endpoint)
        elif legacy in ('unreachable', 'error'):
            warnings.append('probe réseau 22 non concluante sur ' + endpoint)
        # La fermeture locale toutes interfaces est contrôlée séparément.
    return {'fresh_key_authentication': fresh, 'port': port, 'legacy_probes': probes,
            'warnings': warnings, 'failures': errors}


if __name__ == '__main__':
    try:
        config = json.load(sys.stdin)
        mode = config['mode']
        if mode == 'inspect':
            result = inspect(int(config['port']))
        elif mode == 'controller':
            result = controller(config)
        else:
            raise ValueError('mode inconnu')
        print(json.dumps(result, sort_keys=True))
        sys.exit(int(bool(result['failures'])))
    except Exception:
        print('{"failures":["contrôle C14 impossible ; aucune erreur brute affichée"]}')
        sys.exit(1)
