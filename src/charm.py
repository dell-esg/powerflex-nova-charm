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

from ops import model
from ops.main import main
import ops_openstack.plugins.classes

import charmhelpers.core as ch_core
from charmhelpers.core.hookenv import log

from charmhelpers.core.templating import render
from charmhelpers.core.host import service_running

import os

import subprocess

CONNECTOR_DIR = "/opt/emc/scaleio/openstack"
CONNECTOR_FILE = "connector.conf"


class NovaComputePowerFlexCharm(ops_openstack.core.OSBaseCharm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stored.is_started = True

        self.framework.observe(self.on.install, self._on_install)

    def powerflex_configuration(self, charm_config) -> "list[tuple]":
        """Returns the PowerFlex configuration to the caller."""
        cget = charm_config.get

        raw_options = [
            ("volume_backend_name", cget("volume-backend-name")),
            ("san_password", cget("powerflexgw-password")),
            ("replication_device", cget("powerflex-replication-config")),
        ]

        options = [(x, y) for x, y in raw_options if y]
        return options

    def _on_install(self, event):
        super().on_install(event)
        self.create_connector()
        self.install_sdc()
        self.update_status()

    def create_connector(self):
        """Create the connector.conf file and populate with data"""
        config = dict(self.framework.model.config)
        powerflex_backend = dict(self.powerflex_configuration(config))
        powerflex_config = {}
        # Get cinder config stanza name.
        # TODO: Get rid of the hardcoded section name. Relation may be needed with cinder?
        powerflex_config["cinder_name"] = "cinder-dell-powerflex"
        filename = os.path.join(CONNECTOR_DIR, CONNECTOR_FILE)
        ch_core.host.mkdir(CONNECTOR_DIR)

        filter_params = ["san_password"]

        # If replication is enabled, add the filter to the filter_params list
        if "replication_device" in powerflex_backend:
            filter_params.append("replication_device")

        for param in filter_params:
            if param in powerflex_backend:
                if param == "replication_device":
                    # Extract the password from the content 'backendid:acme,san_ip:10.20.30.41,san_login:admin,san_password:password'
                    powerflex_config["rep_san_password"] = (
                        powerflex_backend["replication_device"].split(",")[3].split(":")[1]
                    )
                else:
                    powerflex_config[param] = powerflex_backend[param]

        # Render the templates/connector.conf and create the /opt/emc/scaleio/openstack/connector.conf with root access only
        log("Rendering connector.conf template with config {}".format(powerflex_config))
        rendered_config = render(
            source="connector.conf",
            target=filename,
            context={"backends": powerflex_config},
            perms=0o600,
        )

    def install_sdc(self):
        """Install the SDC debian package in order to get access to the PowerFlex volumes"""
        config = dict(self.framework.model.config)
        sdc_package_file = self.model.resources.fetch("sdc-deb-package")
        # Check if the file exists
        if os.path.isfile(sdc_package_file):
            # Get the MDM IP from config file
            sdc_mdm_ips = config["powerflex-sdc-mdm-ips"]
            # Install the SDC package
            install_cmd = f"sudo MDM_IP={sdc_mdm_ips} dpkg -i {sdc_package_file}"
            log("Installing SDC kernel module with MDM(s) {}".format(sdc_mdm_ips))
            result = subprocess.run(install_cmd.split(), capture_output=True, text=True)
            exit_code = result.returncode
            if exit_code != 0:
                log(
                    "An error occurred during the SDC installation: {}.".format(result.stderr),
                    level=ERROR,
                )
            else:
                log("SDC installed successfully, stdout: {}".format(result.stdout))
                # Check if service scini is running
                if service_running("scini"):
                    log("SDC scini service running. SDC Installation complete.")
                else:
                    log("SDC scini service has encountered errors while starting", level="ERROR")
        else:
            log("The package required for SDC installation is missing.", level="ERROR")
            model.BlockedStatus("SDC package missing")


if __name__ == "__main__":
    main(NovaComputePowerFlexCharm)
