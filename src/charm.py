#! /usr/bin/env python3

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

"""Charmed operator for Dell PowerFlex Nova access."""

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

import ops_openstack.core
import ops_openstack.plugins.classes
from charmhelpers.core.host import mkdir, service_running
from charmhelpers.core.templating import render
from ops import model
from ops.main import main

logger = logging.getLogger(__name__)

CONNECTOR_DIR = "/opt/emc/scaleio/openstack"
CONNECTOR_FILE = "connector.conf"


class NovaComputePowerFlexCharm(ops_openstack.core.OSBaseCharm):
    """Charm which provides PowerFlex access to Nova."""

    RESTART_MAP = {
        str(Path(CONNECTOR_DIR, CONNECTOR_FILE)): ["scini"],
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stored.installed = False
        self._stored.install_failed = False
        self._stored.is_started = True
        self._stored.sdc_package_name = None

        self.register_status_check(self.resource_status)
        self.register_status_check(self.install_status)

        self.framework.observe(self.on.remove, self.on_remove)

    def _get_debian_package_path(self) -> Optional[Path]:
        """Return the path to the debian package if it has been provided.

        :return: the Path to the debian package if the user has provided it
                 as a resource, otherwise return None
        """
        sdc_package_file = self.model.resources.fetch("sdc-deb-package")

        # Check that the file exists and is not a 0-byte file
        if (
            sdc_package_file.exists()
            and sdc_package_file.is_file()
            and sdc_package_file.stat().st_size > 0
        ):
            return sdc_package_file

        return None

    def resource_status(self) -> model.StatusBase:
        """Return the resource status for the debian package.

        :return: ActiveStatus when the debian file package has been provided
                 as a resource, BlockedStatus when the user needs to provide
                 the package.
        """
        if self._get_debian_package_path():
            return model.ActiveStatus()

        return model.BlockedStatus("sdc-deb-package resource is missing")

    def install_status(self):
        """Return the status for the deb installation.

        :return: ActiveStatus when the installation of the debian file is successful,
                 BlockedStatus when the installation failed.
        """
        if self._stored.installed:
            return model.ActiveStatus()

        # TODO: This should really be checked by examining the dpkg install state
        if self._stored.install_failed:
            return model.BlockedStatus("SDC Debian package failed to install")

        return model.BlockedStatus("SDC Debian package is not installed")

    def powerflex_configuration(self, charm_config) -> "list[tuple]":
        """Return the PowerFlex configuration to the caller."""
        cget = charm_config.get

        raw_options = [
            ("volume_backend_name", cget("volume-backend-name")),
            ("san_password", cget("powerflexgw-password")),
            ("replication_device", cget("powerflex-replication-config")),
        ]

        options = [(x, y) for x, y in raw_options if y]
        return options

    def on_install(self, event):
        super().on_install(event)
        self.create_connector()
        self.install_sdc()
        self.update_status()

    def on_remove(self, event):
        """Handle the remove event."""
        self.remove_connector()
        if self.uninstall_sdc():
            # Update the stored state to be tidy, but realistically this won't
            # end up being used, given that the charm is being removed.
            self._stored.installed = False
            self._stored.install_failed = False
            self._stored.is_started = False

        # Similarly, the status of the unit will only momentarily be relevant,
        # since the unit is about to be removed, but we update it to be tidy.
        self.update_status()

    def create_connector(self):
        """Create the connector.conf file and populate with data."""
        config = dict(self.framework.model.config)
        powerflex_backend = dict(self.powerflex_configuration(config))
        powerflex_config = {}
        # Get cinder config stanza name.
        # TODO: Get rid of the hardcoded section name.
        powerflex_config["cinder_name"] = "cinder-dell-powerflex"
        filename = os.path.join(CONNECTOR_DIR, CONNECTOR_FILE)
        mkdir(CONNECTOR_DIR)

        filter_params = ["san_password"]

        # If replication is enabled, add the filter to the filter_params list
        if "replication_device" in powerflex_backend:
            filter_params.append("replication_device")

        for param in filter_params:
            if param in powerflex_backend:
                if param == "replication_device":
                    # Extract the password from the content
                    # 'backendid:acme,san_ip:10.20.30.41,san_login:admin,san_password:password'
                    powerflex_config["rep_san_password"] = (
                        powerflex_backend["replication_device"].split(",")[3].split(":")[1]
                    )
                else:
                    powerflex_config[param] = powerflex_backend[param]

        # Render the templates/connector.conf and
        # create the /opt/emc/scaleio/openstack/connector.conf
        # with root access only.
        logger.info("Rendering connector.conf template with config %s", str(powerflex_config))
        render(
            source="connector.conf",
            target=filename,
            context={"backends": powerflex_config},
            perms=0o600,
        )

    def remove_connector(self):
        """Remove the connector.conf file, if it exists."""
        connector_file_path = os.path.join(CONNECTOR_DIR, CONNECTOR_FILE)
        if os.path.exists(connector_file_path):
            os.remove(connector_file_path)
            logger.info("Removed connector.conf file at %s", connector_file_path)

    def install_sdc(self):
        """Enable access to the PowerFlex volumes."""
        config = dict(self.framework.model.config)
        sdc_package_file = self._get_debian_package_path()
        if not sdc_package_file:
            # Note: the user has not provided that debian resource
            logger.error("The package required for SDC installation is missing")
            return

        # Store the name of the SDC package for later use.
        result = subprocess.run(
            ["dpkg", "--info", str(sdc_package_file)],
            capture_output=True,
            text=True,
        )
        mo = re.search(r"^\s*Package:\s+(.+?)$", result.stdout, re.MULTILINE)
        if mo:
            self._stored.sdc_package_name = mo.group(1)
        else:
            logger.warning("Couldn't determine package name from %s", sdc_package_file)

        # Get the MDM IP from config file
        sdc_mdm_ips = config["powerflex-sdc-mdm-ips"]
        # Install the SDC package
        install_cmd = ["sudo", f"MDM_IP={sdc_mdm_ips}", "dpkg", "-i", str(sdc_package_file)]
        logger.info("Installing SDC kernel module with MDM(s) %s", sdc_mdm_ips)
        self.model.unit.status = model.MaintenanceStatus("Installing SDC kernel module")
        result = subprocess.run(install_cmd, capture_output=True, text=True)
        exit_code = result.returncode

        # If the installation process failed, then log the error and return
        # The install_status() status check method will determine that there is
        # an error based on the self._stored.install_failed flag and report the
        # error.
        if exit_code != 0:
            logger.error("An error occurred during the SDC installation: %s", result.stderr)
            self._stored.installed = False
            self._stored.install_failed = True
            return

        self._stored.installed = True
        self._stored.install_failed = False
        logger.info("SDC installed successfully, stdout: %s", result.stdout)
        # Check if service scini is running
        if service_running("scini"):
            logger.info("SDC scini service running. SDC Installation complete.")
        else:
            logger.error("SDC scini service has encountered errors while starting")

    def uninstall_sdc(self):
        """Remove the SDC package if it is installed."""
        if not self._stored.installed:
            # Not installed is 'success'.
            return True
        if not self._stored.sdc_package_name:
            logger.error("SDC package name is not stored, cannot remove SDC package")
            return False
        remove_cmd = ["sudo", "apt", "remove", "-y", self._stored.sdc_package_name]
        result = subprocess.run(remove_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("Failed to remove SDC package: %r", result.stderr)
            # We just exit here: it's not critical that the package is
            # removed, and we don't want to block the charm removal by
            # erroring on the remove event. The Juju log will show that the
            # package removal failed, and the user can take action if needed.
            return False
        logger.info("SDC package removed successfully: %r", result.stdout)
        return True


if __name__ == "__main__":
    main(NovaComputePowerFlexCharm)  # pragma: no cover
