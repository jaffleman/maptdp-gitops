"""C13 : archivage Vault + backup SQLite + rotation native, sans secret en argv.

Phases explicites prepare/rotate/verify. Un marqueur root-only sur le CP permet
de reprendre après archivage interrompu sans répéter une rotation déjà faite.
La sauvegarde SQLite reste locale au CP ; le token est archivé hors CP dans Vault.
"""
import argparse
import datetime as dt
import hmac
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request


def require(ok, message):
    if not ok:
        raise ValueError(message)


def needs_rotation(phase, same_token):
    require(phase in ('prepared', 'intent', 'rotated'), 'marqueur non pris en charge')
    require(phase != 'prepared' or same_token, 'token modifié hors de cette rotation ; arrêt')
    require(phase != 'rotated' or not same_token, 'marqueur et token incohérents ; arrêt')
    return same_token


def load_session(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and
            stat.S_IMODE(info.st_mode) == 0o600, 'session Vault non sûre')
    data = json.loads(path.read_text())
    require(data['vault_addr'] == 'http://100.91.75.58:8200', 'destination Vault non attendue')
    require(data['expires_at'] > time.time(), 'session locale expirée ; refaire la saisie masquée')
    return data


class Vault:
    def __init__(self, session):
        self.s = session
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, path, body=None):
        require(self.s['expires_at'] > time.time(), 'session locale expirée ; reprise possible avec la même rotation-id')
        request = urllib.request.Request(self.s['vault_addr'] + '/v1/' + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'X-Vault-Token': self.s['token'], 'Content-Type': 'application/json'})
        with self.opener.open(request, timeout=20) as response:
            return json.load(response)

    def read(self, path):
        return self.request('k3s/data/' + path)['data']['data']

    def archive(self, path, data):
        try:
            previous = self.read(path)
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
            self.request('k3s/data/' + path, {'options': {'cas': 0}, 'data': data})
            previous = self.read(path)
        require(previous == data, 'archive Vault existante différente ; aucun écrasement')


REMOTE = r'''
import base64, datetime, hmac, json, os, pathlib, re, sqlite3, ssl, subprocess, sys, time, urllib.request, urllib.error
c=json.load(sys.stdin)
rid=c['rotation_id']
if not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z',rid): raise ValueError('rotation id invalide')
root=pathlib.Path('/var/backups/k3s')
folder=root/('c13-'+rid)
marker=folder/'rotation.json'
token_path=pathlib.Path('/var/lib/rancher/k3s/server/token')
def run(args,timeout=30):
 r=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 if r.returncode: raise ValueError('commande distante échouée')
 return r.stdout
def save(state):
 temp=folder/'rotation.json.tmp'
 fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'w') as f:
  json.dump(state,f);f.flush();os.fsync(f.fileno())
 os.replace(temp,marker)
action=c['action']
if action=='inspect':
 ns={};exec(c['preflight_source'],ns)
 report=ns['report']('server')
 if not (report['default_layout_supported'] and report['service_active'] and report['sqlite_present'] and not report['etcd_present'] and not report['datastore_configured'] and not report['server_env_has_fixed_token'] and not report['server_config_has_fixed_token']):raise ValueError('layout serveur refusé')
 uid=json.loads(run(['/usr/local/bin/k3s','kubectl','--kubeconfig','/etc/rancher/k3s/k3s.yaml','--request-timeout=15s','get','namespace','kube-system','-o','json']))['metadata']['uid']
 nodes=json.loads(run(['/usr/local/bin/k3s','kubectl','--kubeconfig','/etc/rancher/k3s/k3s.yaml','--request-timeout=15s','get','nodes','-o','json']))['items']
 if len([n for n in nodes if 'node-role.kubernetes.io/control-plane' in n['metadata'].get('labels',{})])!=1: raise ValueError('un seul CP requis')
 print(json.dumps({'token':token_path.read_text().strip(),'cluster_uid':uid,'version':report['version']}))
elif action=='prepare':
 if folder.exists():
  state=json.loads(marker.read_text())
  if state['vault_base']!=c['vault_base'] or state['phase']!='prepared':raise ValueError('préparation déjà dépassée ; ne pas recommencer')
 else:
  folder.mkdir(parents=True,mode=0o700)
  os.chmod(folder,0o700)
  destination=folder/'state.db'
  fd=os.open(destination,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
  source=sqlite3.connect('file:/var/lib/rancher/k3s/server/db/state.db?mode=ro',uri=True,timeout=20)
  backup=sqlite3.connect(str(destination),timeout=20)
  deadline=time.monotonic()+180
  def progress(status,remaining,total):
   if time.monotonic()>deadline:raise ValueError('backup SQLite trop long')
  try:
   source.backup(backup,pages=256,progress=progress,sleep=0.05)
   if backup.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('backup SQLite invalide')
  finally:backup.close();source.close()
  state={'phase':'prepared','rotation_id':rid,'vault_base':c['vault_base'],'cluster_uid':c['cluster_uid'],'sqlite_backup':str(destination)}
  save(state)
 print(json.dumps({'phase':state['phase'],'sqlite_backup':state['sqlite_backup'],'backup_bytes':(folder/'state.db').stat().st_size}))
elif action=='state':
 state=json.loads(marker.read_text());print(json.dumps(state))
elif action=='intent':
 state=json.loads(marker.read_text())
 if state['phase'] not in ('prepared','intent'):raise ValueError('état rotation inattendu')
 if not hmac.compare_digest(token_path.read_text().strip(),c['old_token']):raise ValueError('token déjà modifié')
 state['phase']='intent';save(state);print('{"intent_recorded":true}')
elif action=='rotate':
 state=json.loads(marker.read_text())
 if state['phase']!='intent' or not hmac.compare_digest(token_path.read_text().strip(),c['old_token']):raise ValueError('rotation non autorisée par marqueur')
 run(['/usr/local/bin/k3s','token','rotate'],timeout=90)
 if hmac.compare_digest(token_path.read_text().strip(),c['old_token']):raise ValueError('token inchangé après rotation')
 state['phase']='rotated';save(state);print('{"native_rotation_done":true}')
elif action=='mark_rotated':
 state=json.loads(marker.read_text())
 if state['phase'] not in ('intent','rotated') or hmac.compare_digest(token_path.read_text().strip(),c['old_token']):raise ValueError('reprise incohérente')
 state['phase']='rotated';save(state);print('{"rotation_recorded":true}')
elif action=='read_token':
 print(json.dumps({'token':token_path.read_text().strip()}))
elif action=='restart':
 state=json.loads(marker.read_text())
 if state['phase']!='rotated':raise ValueError('rotation non enregistrée')
 run(['systemctl','restart','k3s'],timeout=180)
 run(['systemctl','is-active','k3s'])
 print('{"server_restarted":true}')
elif action=='verify':
 state=json.loads(marker.read_text())
 context=ssl.create_default_context(cafile='/var/lib/rancher/k3s/server/tls/server-ca.crt')
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context))
 def status(token):
  credential=token.split('::',1)[1]
  req=urllib.request.Request('https://127.0.0.1:6443/v1-k3s/server-bootstrap',headers={'Authorization':'Basic '+base64.b64encode(credential.encode()).decode()})
  try:
   with opener.open(req,timeout=15) as r:return r.status
  except urllib.error.HTTPError as e:return e.code
 current=token_path.read_text().strip()
 good=status(current);old=status(c['old_token'])
 if good!=200 or old not in (401,403):raise ValueError('vérification ancien/nouveau token non conforme')
 state['verified']=True;save(state)
 print(json.dumps({'new_token_http':good,'old_token_http':old,'verified':True}))
else:raise ValueError('action inconnue')
'''


class Server:
    def __init__(self, args):
        self.args = args

    def call(self, action, **data):
        payload = dict(data, action=action, rotation_id=self.args.rotation_id)
        args = ['ssh', '-i', str(Path.home()/'.ssh/ansible_ed25519'), '-p', '63210',
                '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=15',
                '-o', 'ServerAliveInterval=10', '-o', 'ServerAliveCountMax=2',
                'ubuntu@' + self.args.host, shlex.join(['sudo', '-n', 'python3', '-c', REMOTE])]
        result = subprocess.run(args, input=json.dumps(payload), capture_output=True, text=True, timeout=240)
        require(result.returncode == 0, 'action distante échouée : ' + action + ' ; aucune erreur brute affichée')
        return json.loads(result.stdout)


def main(args):
    require(re.fullmatch(r'[0-9]{8}T[0-9]{6}Z', args.rotation_id), 'rotation-id invalide')
    require(re.fullmatch(r'100\.[0-9]+\.[0-9]+\.[0-9]+', args.host), 'hôte tailnet attendu')
    session_path = Path('/dev/shm') / ('maptdp-c13-vault-%d.json' % os.getuid())
    vault = Vault(load_session(session_path))
    server = Server(args)
    preflight_source = Path(__file__).with_name('k3s_token_preflight.py').read_text()
    if args.phase == 'prepare':
        inspect = server.call('inspect', preflight_source=preflight_source)
        base = 'infra/maptdp/server-tokens/' + inspect['cluster_uid'] + '/' + args.rotation_id
        before = {'server_token': inspect['token'], 'cluster_uid': inspect['cluster_uid'],
                  'rotation_id': args.rotation_id, 'phase': 'before', 'version': inspect['version']}
        vault.archive(base + '/before', before)
        print('OK | Token avant rotation archivé et relu dans Vault | k3s/' + base + '/before', flush=True)
        result = server.call('prepare', vault_base=base, cluster_uid=inspect['cluster_uid'])
        print('OK | Copie SQLite locale cohérente | ' + json.dumps(result), flush=True)
    else:
        state = server.call('state')
        base = state['vault_base']
        before = vault.read(base + '/before')
        old = before['server_token']
        if args.phase == 'rotate':
            current = server.call('read_token')['token']
            if needs_rotation(state['phase'], hmac.compare_digest(current, old)):
                server.call('inspect', preflight_source=preflight_source)
                server.call('intent', old_token=old)
                server.call('rotate', old_token=old)
                print('OK | Rotation native effectuée, valeur non affichée', flush=True)
            else:
                server.call('mark_rotated', old_token=old)
                print('OK | Rotation déjà effectuée : reprise sans nouvelle rotation', flush=True)
            new = server.call('read_token')['token']
            require(not hmac.compare_digest(old, new), 'nouveau token identique')
            after = dict(before, server_token=new, phase='after')
            vault.archive(base + '/after', after)
            print('OK | Nouveau token archivé et relu dans Vault | k3s/' + base + '/after', flush=True)
            server.call('restart')
            print('OK | Serveur k3s redémarré et actif', flush=True)
        else:
            after = vault.read(base + '/after')
            current = server.call('read_token')['token']
            require(hmac.compare_digest(current, after['server_token']), 'token courant différent de l’archive après')
            result = server.call('verify', old_token=old)
            print('OK | Vérification contrôlée | ' + json.dumps(result), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--rotation-id', required=True)
    parser.add_argument('--phase', choices=['prepare', 'rotate', 'verify'], required=True)
    args = parser.parse_args()
    try:
        main(args)
    except Exception as error:
        # Ne jamais imprimer les exceptions HTTP/subprocess ou leur corps.
        message = str(error) if isinstance(error, ValueError) else type(error).__name__
        print('ECHEC C13 | ' + message + ' | conserver la même rotation-id pour reprise', flush=True)
        sys.exit(1)
