import unittest
from c13_rotate_server import needs_rotation, verification_ok


class RotationStateTests(unittest.TestCase):
    def test_prepared_and_same_token_requires_rotation(self):
        self.assertTrue(needs_rotation('prepared', True))

    def test_external_change_before_intent_refuses_rotation(self):
        with self.assertRaises(ValueError):
            needs_rotation('prepared', False)

    def test_resume_after_interruption_does_not_rotate_twice(self):
        self.assertFalse(needs_rotation('intent', False))
        self.assertFalse(needs_rotation('rotated', False))

    def test_intent_before_native_call_can_resume(self):
        self.assertTrue(needs_rotation('intent', True))

    def test_inconsistent_or_unknown_marker_refuses_rotation(self):
        for phase, same in [('rotated', True), ('unknown', False)]:
            with self.assertRaises(ValueError):
                needs_rotation(phase, same)

    def test_authenticated_but_unsupported_endpoint_is_not_success(self):
        self.assertFalse(verification_ok(400, 401))
        self.assertFalse(verification_ok(200, 200))
        self.assertFalse(verification_ok(200, 404))

    def test_positive_control_and_revoked_old_credential(self):
        self.assertTrue(verification_ok(200, 401))
        self.assertTrue(verification_ok(200, 403))


if __name__ == '__main__':
    unittest.main()
