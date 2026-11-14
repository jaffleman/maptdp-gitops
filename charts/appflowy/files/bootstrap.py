"""Create credentials once; preserve them across retries, resyncs and upgrades."""
import base64
import json
import os
from pathlib import Path
import secrets
import ssl
import urllib.error
import urllib.request

REQUIRED = ('postgres-password', 'redis-password', 'root-user', 'root-password',
            'jwt-secret', 'admin-password')


def validate(document):
    data = document.get('data', {})
    if any(not data.get(key) for key in REQUIRED):
        raise RuntimeError('Existing credential Secret is incomplete; refusing to replace it')
    return document


def ensure_credentials(request, name, namespace):
    try:
        validate(request('GET', '/' + name))
        return 'Existing credentials preserved'
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
    values = {key: secrets.token_hex(32) for key in REQUIRED}
    values['root-user'] = 'appflowy' + secrets.token_hex(8)
    document = {'apiVersion': 'v1', 'kind': 'Secret', 'type': 'Opaque',
                'metadata': {'name': name, 'namespace': namespace,
                             'labels': {'app.kubernetes.io/part-of': 'appflowy'}},
                'data': {key: base64.b64encode(value.encode()).decode()
                         for key, value in values.items()}}
    try:
        request('POST', '', document)
        return 'Initial credentials created'
    except urllib.error.HTTPError as error:
        if error.code != 409:
            raise
        validate(request('GET', '/' + name))
        return 'Concurrent creation detected; existing credentials preserved'


def main():
    directory = Path('/var/run/secrets/kubernetes.io/serviceaccount')
    namespace = directory.joinpath('namespace').read_text().strip()
    token = directory.joinpath('token').read_text().strip()
    context = ssl.create_default_context(cafile=str(directory / 'ca.crt'))
    base = ('https://' + os.environ['KUBERNETES_SERVICE_HOST'] + ':' +
            os.environ['KUBERNETES_SERVICE_PORT_HTTPS'] +
            '/api/v1/namespaces/' + namespace + '/secrets')

    def request(method, suffix, body=None):
        payload = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base + suffix, data=payload, method=method,
                                     headers={'Authorization': 'Bearer ' + token,
                                              'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, context=context, timeout=30) as result:
            return json.load(result)

    print(ensure_credentials(request, os.environ['SECRET_NAME'], namespace))


if __name__ == '__main__':
    main()
