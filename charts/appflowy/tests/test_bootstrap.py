import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError

spec = importlib.util.spec_from_file_location('bootstrap', Path(__file__).parents[1] / 'files/bootstrap.py')
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


def error(code):
    return HTTPError('https://kubernetes/secret', code, 'test', {}, None)


class CredentialBootstrapTests(unittest.TestCase):
    def test_existing_secret_is_never_modified(self):
        request = Mock(return_value={'data': {k: 'existing' for k in bootstrap.REQUIRED}})
        bootstrap.ensure_credentials(request, 'credentials', 'preprod')
        request.assert_called_once_with('GET', '/credentials')

    def test_missing_secret_creates_all_required_keys(self):
        request = Mock(side_effect=[error(404), {}])
        bootstrap.ensure_credentials(request, 'credentials', 'preprod')
        method, suffix, body = request.call_args.args
        self.assertEqual((method, suffix), ('POST', ''))
        self.assertEqual(body['metadata']['namespace'], 'preprod')
        self.assertEqual(set(body['data']), set(bootstrap.REQUIRED))
        self.assertNotIn('ownerReferences', body['metadata'])

    def test_concurrent_creation_preserves_winning_secret(self):
        request = Mock(side_effect=[error(404), error(409), {'data': {k: 'winner' for k in bootstrap.REQUIRED}}])
        bootstrap.ensure_credentials(request, 'credentials', 'preprod')
        self.assertEqual([c.args[0] for c in request.call_args_list], ['GET', 'POST', 'GET'])

    def test_incomplete_secret_fails_without_rotating_credentials(self):
        request = Mock(return_value={'data': {'jwt-secret': 'existing'}})
        with self.assertRaises(RuntimeError):
            bootstrap.ensure_credentials(request, 'credentials', 'preprod')
        self.assertEqual(request.call_count, 1)

    def test_permission_error_is_not_treated_as_missing_secret(self):
        request = Mock(side_effect=error(403))
        with self.assertRaises(HTTPError):
            bootstrap.ensure_credentials(request, 'credentials', 'preprod')
        self.assertEqual(request.call_count, 1)


if __name__ == '__main__':
    unittest.main()
