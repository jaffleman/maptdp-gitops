import unittest
from unittest.mock import patch

from ssh_postconditions import listening_ports, firewall_posture, local_failures, controller


class SSHPostconditionsTests(unittest.TestCase):
    def clean(self):
        return {'sshd_syntax_valid': True, 'configured_ports': [63210], 'listen22': False,
                'listen_target': True, 'ssh_service_active': True, 'ssh_service_enabled': True,
                'ssh_socket_inactive_disabled': True,
                'firewall': {'active': True, 'incoming_default_deny': True, 'explicit_allow22': False,
                             'deny22_ipv4': True, 'deny22_ipv6': True, 'ipv6_enabled': True}}

    def test_ipv4_ipv6_and_lookalike_ports(self):
        rows='LISTEN 0 128 0.0.0.0:63210 0.0.0.0:*\nLISTEN 0 128 [::]:22 [::]:*\nLISTEN 0 128 127.0.0.1:122 [::]:*'
        self.assertEqual(listening_ports(rows), {22, 122, 63210})

    def test_residual_allow22_is_rejected_even_with_deny(self):
        text='Status: active\nDefault: deny (incoming)\n22/tcp DENY IN Anywhere\n22/tcp ALLOW IN Anywhere\n22/tcp (v6) DENY IN Anywhere (v6)'
        report=self.clean(); report['firewall']=firewall_posture(text,True)
        self.assertIn('posture UFW IPv4 du port 22 non conforme', local_failures(report,63210))

    def test_v6_deny_required_when_v6_enabled(self):
        report=self.clean(); report['firewall']['deny22_ipv6']=False
        self.assertTrue(local_failures(report,63210))
        report['firewall']['ipv6_enabled']=False
        self.assertEqual(local_failures(report,63210),[])

    def test_listener22_is_failure_even_behind_firewall(self):
        report=self.clean(); report['listen22']=True
        self.assertTrue(local_failures(report,63210))

    def test_socket_or_extra_config_port_cannot_pass(self):
        report=self.clean(); report['ssh_socket_inactive_disabled']=False
        self.assertTrue(local_failures(report,63210))
        report=self.clean(); report['configured_ports']=[22,63210]
        self.assertTrue(local_failures(report,63210))

    def test_clean_posture_passes(self):
        self.assertEqual(local_failures(self.clean(),63210),[])

    def config(self):
        return {'host':'100.64.0.2','port':63210,'user':'ubuntu','identity_file':'/test/key',
                'public_addresses':['2001:db8::2']}

    def test_no_route_is_explicitly_inconclusive_not_claimed_closed(self):
        with patch('ssh_postconditions.run',return_value=(0,'ubuntu')) as call, \
             patch('ssh_postconditions.probe',side_effect=['refused','unreachable']):
            result=controller(self.config())
            self.assertEqual(result['failures'],[])
            self.assertTrue(result['warnings'])
            args=call.call_args.args[0]
            self.assertIn('ControlPath=none',args)
            self.assertIn('StrictHostKeyChecking=yes',args)
            self.assertIn('PasswordAuthentication=no',args)

    def test_open_public22_fails_even_if_fresh_auth_works(self):
        with patch('ssh_postconditions.run',return_value=(0,'ubuntu')), \
             patch('ssh_postconditions.probe',return_value='open'):
            self.assertTrue(controller(self.config())['failures'])

    def test_old_cached_connection_cannot_substitute_failed_fresh_auth(self):
        with patch('ssh_postconditions.run',return_value=(255,'')), \
             patch('ssh_postconditions.probe',return_value='refused'):
            self.assertTrue(controller(self.config())['failures'])


if __name__=='__main__':
    unittest.main()
