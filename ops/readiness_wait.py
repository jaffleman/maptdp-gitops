"""C10 : attentes bornées, états structurés et erreurs sans réponse brute.

Kubernetes : GET seulement. APT : tester brièvement les verrous POSIX existants,
sans créer/tronquer/supprimer de fichier ni interrompre un processus.
"""
import errno
import json
import os
import subprocess
import sys
import time

APT_LOCKS = ['/var/lib/dpkg/lock-frontend', '/var/lib/dpkg/lock',
             '/var/lib/apt/lists/lock', '/var/cache/apt/archives/lock']


def mapping(value):
    return value if isinstance(value, dict) else {}


def node_state(obj):
    conditions = mapping(mapping(obj).get('status')).get('conditions') or []
    ready = any(mapping(c).get('type') == 'Ready' and mapping(c).get('status') == 'True' for c in conditions)
    return {'ready': ready, 'reason': 'Node Ready=True' if ready else 'Node Ready=True absent ou faux'}


def deployment_state(obj):
    obj = mapping(obj)
    spec, status, meta = mapping(obj.get('spec')), mapping(obj.get('status')), mapping(obj.get('metadata'))
    desired = spec.get('replicas', 1)
    observed, generation = status.get('observedGeneration', 0), meta.get('generation', 1)
    positive = isinstance(desired, int) and desired > 0
    current = isinstance(observed, int) and isinstance(generation, int) and observed >= generation
    counts = {key: status.get(key, 0) for key in ['replicas', 'updatedReplicas', 'readyReplicas', 'availableReplicas']}
    ready = positive and current and all(value == desired for value in counts.values())
    return {'ready': ready, 'desired': desired, 'observed_generation': observed,
            'generation': generation, 'replicas': counts,
            'reason': 'Deployment actualisé et disponible' if ready else 'Deployment incomplet, génération ancienne ou réplicas insuffisants'}


def application_state(obj):
    status = mapping(mapping(obj).get('status'))
    sync = mapping(status.get('sync')).get('status')
    health = mapping(status.get('health')).get('status')
    phase = mapping(status.get('operationState')).get('phase')
    ready = sync == 'Synced' and health == 'Healthy' and phase not in ('Running', 'Terminating', 'Failed', 'Error')
    return {'ready': ready,
            'sync': sync if sync in ('Synced', 'OutOfSync', 'Unknown') else 'Unknown',
            'health': health if health in ('Healthy', 'Progressing', 'Degraded', 'Missing', 'Suspended', 'Unknown') else 'Unknown',
            'operation': phase if phase in ('Running', 'Terminating', 'Failed', 'Error', 'Succeeded') else 'non renseignée',
            'reason': 'Application Synced/Healthy' if ready else 'Application absente/incomplète ou non Synced/Healthy/opération terminée'}


def apt_state(paths=None):
    import fcntl
    descriptors, locked = [], []
    try:
        for path in APT_LOCKS if paths is None else paths:
            try:
                fd = os.open(path, os.O_RDWR | os.O_CLOEXEC)
            except FileNotFoundError:
                continue
            except OSError:
                return {'ready': False, 'terminal': True, 'reason': 'verrou APT inaccessible : ' + path}
            descriptors.append(fd)
            try:
                fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                if error.errno in (errno.EAGAIN, errno.EACCES):
                    locked.append(path)
                else:
                    return {'ready': False, 'terminal': True, 'reason': 'test de verrou APT impossible : ' + path}
        return {'ready': not locked, 'locked_paths': locked,
                'reason': 'verrous APT libres' if not locked else 'verrou APT occupé ; identifier le processus détenteur'}
    finally:
        for fd in descriptors:
            # Fermer un descripteur relâche les verrous acquis par ce processus.
            os.close(fd)


def kubectl(config, args, deadline):
    budget = min(float(config.get('request_timeout', 10)), deadline - time.monotonic())
    if budget < 0.005:
        return None, 'budget de requête épuisé'
    cmd = ['kubectl', '--kubeconfig', config['kubeconfig'],
           '--request-timeout=%.3fs' % budget] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=budget, check=False)
    except subprocess.TimeoutExpired:
        return None, 'délai de requête API dépassé'
    except OSError:
        return None, 'kubectl indisponible'
    if result.returncode:
        text = result.stderr.lower()
        if 'notfound' in text or 'not found' in text:
            reason = 'ressource absente'
        elif 'forbidden' in text or 'unauthorized' in text:
            reason = 'accès Kubernetes refusé'
        elif 'connection refused' in text:
            reason = 'connexion API refusée'
        else:
            reason = 'lecture Kubernetes échouée'
        return None, reason
    return result.stdout, ''


def poll(config, deadline):
    kind = config['kind']
    if kind == 'apt':
        return apt_state()
    resources = {'node': 'node', 'deployment': 'deployment.apps', 'application': 'application.argoproj.io'}
    args = ['get', resources[kind], config['name'], '-o', 'json']
    if config.get('namespace'):
        args += ['-n', config['namespace']]
    text, error = kubectl(config, args, deadline)
    if text is None:
        return {'ready': False, 'reason': error}
    try:
        obj = json.loads(text)
    except (ValueError, TypeError):
        return {'ready': False, 'reason': 'réponse JSON Kubernetes inexploitable'}
    state = {'node': node_state, 'deployment': deployment_state, 'application': application_state}[kind](obj)
    if kind == 'node' and state['ready']:
        response, error = kubectl(config, ['get', '--raw=/readyz'], deadline)
        state['api_ready'] = response is not None and response.strip() == 'ok'
        state['ready'] = state['ready'] and state['api_ready']
        if not state['api_ready']:
            state['reason'] = error or 'API /readyz non prête'
    return state


def wait_until(probe, timeout, interval, clock=time.monotonic, sleep=time.sleep):
    start = clock()
    deadline = start + timeout
    attempts, last = 0, {'ready': False, 'reason': 'aucune tentative'}
    while clock() < deadline:
        attempts += 1
        last = probe(deadline)
        now = clock()
        if last.get('ready') and now <= deadline:
            return {'ok': True, 'attempts': attempts, 'elapsed_seconds': round(now-start, 3), 'last_state': last}
        if last.get('terminal'):
            break
        remaining = deadline - now
        if remaining <= 0:
            break
        sleep(min(interval, remaining))
    return {'ok': False, 'attempts': attempts, 'elapsed_seconds': round(clock()-start, 3),
            'last_state': last, 'reason': 'échec terminal' if last.get('terminal') else 'échéance globale dépassée'}


def main(config):
    kind = config['kind']
    timeout, interval = float(config['timeout']), float(config['interval'])
    request = float(config.get('request_timeout', 10))
    if kind not in ('apt', 'node', 'deployment', 'application') or not 0 < timeout <= 3600 or interval <= 0 or request <= 0:
        raise ValueError('paramètres C10 invalides')
    if kind != 'apt' and (not config.get('name') or not config.get('kubeconfig')):
        raise ValueError('cible ou kubeconfig C10 absent')
    result = wait_until(lambda deadline: poll(config, deadline), timeout, interval)
    result.update(kind=kind, name=config.get('name', ''), namespace=config.get('namespace', ''), timeout_seconds=timeout)
    return result


if __name__ == '__main__':
    try:
        result = main(json.load(sys.stdin))
        print(json.dumps(result, sort_keys=True))
        sys.exit(0 if result['ok'] else 1)
    except Exception:
        print('{"ok":false,"reason":"contrôle C10 impossible ; vérifier les paramètres et droits, aucune réponse brute affichée"}')
        sys.exit(1)
