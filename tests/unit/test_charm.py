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
from unittest.mock import patch

import ops
import ops.testing

from charm import NovaComputePowerFlexCharm


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = ops.testing.Harness(NovaComputePowerFlexCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.charm = self.harness.charm

    @patch("charmhelpers.core.host.mkdir")
    @patch("charm.render")
    def test_create_connector(self, _render, _mkdir):
        """Test the connector renders non-replication settings."""
        self.harness.disable_hooks()
        self.charm.create_connector()
        _mkdir.assert_called_once_with("/opt/emc/scaleio/openstack")
        _render.assert_called_once_with(
            source="connector.conf",
            target="/opt/emc/scaleio/openstack/connector.conf",
            context = ({"backends": {"cinder_name": "cinder-dell-powerflex",
                                     "san_password": "password"}
                }
            ),
            perms=0o600,
    )

    @patch("charmhelpers.core.host.mkdir")
    @patch("charm.render")
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
                    "cinder_name": "cinder-dell-powerflex",
                    "san_password": "password",
                    "rep_san_password": "password",
                }
            },
            perms=0o600,
        )
