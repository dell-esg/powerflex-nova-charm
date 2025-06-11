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
from unittest.mock import MagicMock, patch

import ops
import ops.testing
from ops.model import ActiveStatus, BlockedStatus

from charm import NovaComputePowerFlexCharm


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = ops.testing.Harness(NovaComputePowerFlexCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.add_resource("sdc-deb-package", "test-content")
        self.harness.update_config(
            {
                "powerflex-sdc-mdm-ips": "192.168.0.0",
            }
        )
        self.harness.begin()
        self.charm = self.harness.charm

    def test__on_install(self):
        """Tests on installation the necessary methods are called."""
        # Don't want any actual installations occurring so mock it out
        # Note: this comes from the parent class where we simply don't want
        # it trying to alter system state
        self.charm.install_pkgs = MagicMock()
        self.charm.create_connector = MagicMock()
        self.charm.install_sdc = MagicMock()

        # Emit the install hook
        self.charm.on.install.emit()

        self.charm.create_connector.assert_called_once()
        self.charm.install_sdc.assert_called_once()

    def test__on_remove(self):
        """Tests on removal the necessary methods are called."""
        # Don't want any actual installations occurring so mock it out
        # Note: this comes from the parent class where we simply don't want
        # it trying to alter system state
        self.charm.remove_connector = MagicMock()
        self.charm.uninstall_sdc = MagicMock()

        # Emit the remove hook
        self.charm.on.remove.emit()

        self.charm.remove_connector.assert_called_once()
        self.charm.uninstall_sdc.assert_called_once()

    @patch("charm.mkdir")
    @patch("charm.render")
    def test_create_connector(self, _render, _mkdir):
        """Test the connector renders non-replication settings."""
        self.harness.disable_hooks()
        self.charm.create_connector()
        _mkdir.assert_called_once_with("/opt/emc/scaleio/openstack")
        _render.assert_called_once_with(
            source="connector.conf",
            target="/opt/emc/scaleio/openstack/connector.conf",
            context=(
                {"backends": {"cinder_name": "cinder-dell-powerflex", "san_password": "password"}}
            ),
            perms=0o600,
        )

    @patch("charm.mkdir")
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

    @patch("charmhelpers.contrib.openstack.utils.service_running")
    @patch("charm.service_running")
    @patch("subprocess.run")
    def test_install_sdc_resource_attached_running(
        self, _subprocess_run, _service_running, _ch_service_running
    ):
        """Test install sdc when service is running."""
        self.charm.install_pkgs = MagicMock()
        self.charm.create_connector = MagicMock()

        _subprocess_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        _ch_service_running.return_value = True
        _service_running.return_value = True

        self.charm.on.install.emit()

        self.assertEqual(self.charm.unit.status, ActiveStatus("Unit is ready"))

    @patch("charmhelpers.contrib.openstack.utils.service_running")
    @patch("charm.service_running")
    @patch("subprocess.run")
    def test_install_sdc_resource_attached_not_running(
        self, _subprocess_run, _service_running, _ch_service_running
    ):
        """Test install sdc when service fails to start."""
        self.charm.install_pkgs = MagicMock()
        self.charm.create_connector = MagicMock()

        _subprocess_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        _ch_service_running.return_value = False
        _service_running.return_value = False

        self.charm.on.install.emit()

        # Verify the charm goes into BlockedStatus.
        self.assertEqual(
            self.charm.unit.status, BlockedStatus("Services not running that should be: scini")
        )

    @patch("charmhelpers.contrib.openstack.utils.service_running")
    @patch("subprocess.run")
    def test_install_sdc_resource_attached_failed_install(self, _subprocess_run, _service_running):
        """Test failed installation of deb package."""
        self.charm.install_pkgs = MagicMock()
        self.charm.create_connector = MagicMock()

        _subprocess_run.return_value = MagicMock(returncode=128, stdout="", stderr="Error")

        _service_running.return_value = False

        self.charm.on.install.emit()

        self.assertEqual(
            self.charm.unit.status, BlockedStatus("SDC Debian package failed to install")
        )

    def test_install_sdc_resource_not_provided(self):
        """Test resource not provided blocks status."""
        self.harness.add_resource("sdc-deb-package", "")
        self.charm.install_pkgs = MagicMock()
        self.charm.create_connector = MagicMock()

        self.charm.on.install.emit()

        self.assertEqual(
            self.charm.unit.status, BlockedStatus("sdc-deb-package resource is missing")
        )

    @patch("os.path.exists", return_value=True)
    @patch("os.remove")
    def test_remove_connector(self, _remove, _exists):
        """Test the connector removal."""
        self.charm.remove_connector()

        connecter_config_path = "/opt/emc/scaleio/openstack/connector.conf"
        _exists.assert_called_once_with(connecter_config_path)
        _remove.assert_called_once_with(connecter_config_path)

    @patch("subprocess.run")
    def test_uninstall_sdc(self, _subprocess_run):
        """Test uninstalling the SDC package."""
        self.charm._stored.installed = True
        self.charm._stored.install_failed = False
        self.charm._stored.sdc_package_name = "sdc-deb-package"

        _subprocess_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        success = self.charm.uninstall_sdc()

        self.assertTrue(success)
        _subprocess_run.assert_called_once_with(
            ["sudo", "apt", "remove", "-y", "sdc-deb-package"],
            capture_output=True,
            text=True,
        )
