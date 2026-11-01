import unittest
from c13_rotate_server import needs_rotation


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


if __name__ == '__main__':
    unittest.main()
