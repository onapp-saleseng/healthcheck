# README #

### What is this repository for? ###

* An automated quality assurance/validation script for OnApp Enterprise Deployments
* Ver 0.1

### What does this script do? ###

* Checks Control Server OnApp Versions, Kernel Version, CentOS Distribution, Time Zone, and Disk Size
* Checks that the Recovery, Load Balancer, FreeBSD, etc Templates have been downloaded
* Checks Compute Resources can be seen, SSH'd to, SNMP port open, OnApp Version, Kernel, and Distro.
* Checks connectivity between Compute Resources over the management network
* Checks connectivity between Compute Resources over the storage network
* (0.1) Checks network, data store, and backup server joins for each compute zone
* (0.1) Has color all over.

### How do I get set up? ###

* This should be a script which will automatically check, does not require setup besides OnApp being installed.

### Who do I talk to? ###

* Neal Hansen (neal.hansen@onapp.com)
