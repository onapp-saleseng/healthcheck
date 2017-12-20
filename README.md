# README #

### What is this repository for? ###

* An automated quality assurance/validation script for OnApp Enterprise Deployments
* Ver 1.0

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
* Checks network, data store, and backup server joins for each compute zone
* Has color all over.
* Checks CPU of CP and HV's
* Added output example file
* Added creating and destroying a VM as a check (with the -a flag)
* Added failure checking for virtual machine creation
* Formatted hypervisor interconnectivity as a table
* Made output of checks more standard with [+], [-], and [?].
* Abstracted SQL queries further
* Filtered out vCenter/vCloud from network and join checks

### TO DO ###

### How do I get set up? ###

* This should be a bash only script which will automatically check, does not require setup besides OnApp being installed.

### Who do I talk to? ###

* Neal Hansen (neal.hansen@onapp.com)
