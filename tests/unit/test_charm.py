# Copyright 2024 Canonical Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest

import ops
import ops.testing

from charm import CharmNovaPowerflexCharm


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = ops.testing.Harness(CharmNovaPowerflexCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_httpbin_pebble_ready(self):
        # Expected plan after Pebble ready with default config
        expected_plan = {
            "services": {
                "httpbin": {
                    "override": "replace",
                    "summary": "httpbin",
                    "command": "gunicorn -b 0.0.0.0:80 httpbin:app -k gevent",
                    "startup": "enabled",
                    "environment": {"GUNICORN_CMD_ARGS": "--log-level info"},
                }
            },
        }
        # Simulate the container coming up and emission of pebble-ready event
        self.harness.container_pebble_ready("httpbin")
        # Get the plan now we've run PebbleReady
        updated_plan = self.harness.get_container_pebble_plan("httpbin").to_dict()
        # Check we've got the plan we expected
        self.assertEqual(expected_plan, updated_plan)
        # Check the service was started
        service = self.harness.model.unit.get_container("httpbin").get_service("httpbin")
        self.assertTrue(service.is_running())
        # Ensure we set an ActiveStatus with no message
        self.assertEqual(self.harness.model.unit.status, ops.ActiveStatus())

    def test_config_changed_valid_can_connect(self):
        # Ensure the simulated Pebble API is reachable
        self.harness.set_can_connect("httpbin", True)
        # Trigger a config-changed event with an updated value
        self.harness.update_config({"log-level": "debug"})
        # Get the plan now we've run PebbleReady
        updated_plan = self.harness.get_container_pebble_plan("httpbin").to_dict()
        updated_env = updated_plan["services"]["httpbin"]["environment"]
        # Check the config change was effective
        self.assertEqual(updated_env, {"GUNICORN_CMD_ARGS": "--log-level debug"})
        self.assertEqual(self.harness.model.unit.status, ops.ActiveStatus())

    def test_config_changed_valid_cannot_connect(self):
        # Trigger a config-changed event with an updated value
        self.harness.update_config({"log-level": "debug"})
        # Check the charm is in WaitingStatus
        self.assertIsInstance(self.harness.model.unit.status, ops.WaitingStatus)

    def test_config_changed_invalid(self):
        # Ensure the simulated Pebble API is reachable
        self.harness.set_can_connect("httpbin", True)
        # Trigger a config-changed event with an updated value
        self.harness.update_config({"log-level": "foobar"})
        # Check the charm is in BlockedStatus
        self.assertIsInstance(self.harness.model.unit.status, ops.BlockedStatus)

    @patch("charmhelpers.core.host.mkdir") # noqa: F821
    @patch("charm.render") # noqa: F821
    def test_create_connector_with_replication(self, _render, _mkdir):
        """Test the connector renders replication settings."""
        self.harness.update_config(
            {
                "powerflex-replication-config": (
                    "backendid:acme,san_ip:10.20.30.41,san_login:admin,san_password:password"
                )
            }
        )
        _render.reset_mock()
        self.charm.create_connector()
        _render.assert_called_once_with(
            source="connector.conf",
            target="/opt/emc/scaleio/openstack/connector.conf",
            context={
                "backends": {
                    "cinder_name": "cinder-powerflex",
                    "san_password": "password",
                    "rep_san_password": "password",
                }
            },
            perms=0o600,
        )
