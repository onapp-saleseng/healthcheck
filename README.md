# README #

### What is this repository for? ###

* An automated quality assurance/validation script for OnApp Enterprise Deployments
* Ver 0.3.5

### Usage ###

* ./qualitycheck.sh [-h] [-a]
* -h option will only check basic information and skip networking/etc.
* -a option will utilize API to create and destroy a virtual machine automatically

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
* (0.3) Formatted hypervisor interconnectivity as a table
* (0.3) Made output of checks more standard with [+], [-], and [?].
* (0.3.5) Abstracted SQL queries further
* (0.3.5) Foltered out vCenter/vCloud from network and join checks
* (0.3.5) Various small fixes

### TO DO ###

### How do I get set up? ###

* This should be a bash only script which will automatically check, does not require setup besides OnApp being installed.

### Who do I talk to? ###

* Neal Hansen (neal.hansen@onapp.com)
