# Overview

This subordinate charm provides the Dell PowerFlex support to the
[OpenStack Nova Compute service][charm-nova-compute].

# Usage

## Deployment

We are assuming a pre-existing OpenStack deployment.

Deploy nova-compute-powerflex as a subordinate to the nova-compute charm:

    juju deploy --config cinder-config.yaml --resource sdc-deb-package=../EMC-ScaleIO-sdc-4.5-0.287.Ubuntu.22.04.x86_64.deb cinder-powerflex
    juju integrate nova-compute-powerflex:juju-info nova-compute:juju-info
