# README #

### What is this repository for? ###

* An automated quality assurance/validation script for OnApp Enterprise Deployments
* Ver 0.2.5

### What does this script do? ###

* Checks Control Server OnApp Versions, Kernel Version, CentOS Distribution, Time Zone, and Disk Size
* Checks that the Recovery, Load Balancer, FreeBSD, etc Templates have been downloaded
* Checks Compute Resources can be seen, SSH'd to, SNMP port open, OnApp Version, Kernel, and Distro.
* Checks connectivity between Compute Resources over the management network
* Checks connectivity between Compute Resources over the storage network
* (0.1) Checks network, data store, and backup server joins for each compute zone
* (0.1) Has color all over.
* (0.1.1) Checks CPU of CP and HV's
* (0.1.1) Added output example file
* (0.2) Added creating and destroying a VM as a check (with the -a flag)
* (0.2.5) Added failure checking for virtual machine creation

### TO DO ###
* Include some failure detection for VM creation and deletion. Currently will wait forever if it fails to provision. (0.2) - DONE

### How do I get set up? ###

* This should be a script which will automatically check, does not require setup besides OnApp being installed.

### Who do I talk to? ###

* Neal Hansen (neal.hansen@onapp.com)
