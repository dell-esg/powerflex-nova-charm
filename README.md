Dell PowerFlex Storage Backend for Nova
-----------------------------------------
# Overview

This subordinate charm provides the Dell PowerFlex support to the
[OpenStack Nova Compute service][charm-nova-compute].

## Configuration

This section covers common and/or important configuration options. See file `config.yaml` for the full list of options, along with their descriptions and default values. See the [Juju documentation][juju-docs-config-apps] for details on configuring applications.

### `volume-backend-name`

The name of the backend used in cinder configuration. 

### `powerflexgw-password`

The password used to authenticate to the PowerFlex Gateway.

### `powerflex-sdc-mdm-ips`

Specifies a comma-separated list of MDM IPs. Can be used to defined a VIP also. This is required during the SDC configuration.

### `powerflex-replication-config`

Specifies the settings for enabling the replication. Only one replication is supported for each backend.

## Deployment

We are assuming a pre-existing OpenStack deployment.

Deploy nova-compute-powerflex as a subordinate to the nova-compute charm:

    juju deploy --config nova-powerflex-config.yaml --resource sdc-deb-package=../EMC-ScaleIO-sdc-4.5-2.185.Ubuntu.22.04.x86_64.deb cinder-powerflex
    juju integrate nova-compute-powerflex:juju-info nova-compute:juju-info

Depending on the kernel version that your system runs on, you may have to install the proper SDC kernel module.
An alternative method which triggers an on-demand compilation process can be used if your SDC is 3.6.3 and higher or 4.5.2 and higher.
You can refer to the documentation here:
* [On-demand compilation of the PowerFlex SDC driver][sdc]

This charm doesn't include yet the enablement of the on-demand compilation. In case the scini service can't start and your SDC is at version mentioned above, you can enable the feature by creating an empty file on every nodes which runs the SDC driver.
    
    sudo touch /etc/emc/scaleio/scini_sync/.build_scini
    sudo service scini restart

[sdc]: https://www.dell.com/support/kbdoc/en-us/000224134/how-to-on-demand-compilation-of-the-powerflex-sdc-driver    

# Documentation

The OpenStack Charms project maintains two documentation guides:

* [OpenStack Charm Guide][cg]: for project information, including development
  and support notes
* [OpenStack Charms Deployment Guide][cdg]: for charm usage information

[cg]: https://docs.openstack.org/charm-guide
[cdg]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide

# Bugs

Please report bugs on [Launchpad](https://bugs.launchpad.net/charm-nova-powerflex/+filebug).
