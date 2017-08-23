#!/bin/bash

# Script for automatically checking integrity of OnApp installations

# Check for and include the install config file
CFG='/onapp/onapp-cp-install/onapp-cp-install.conf'

if [ -r $CFG ] ; then
	. $CFG
else
	echo 'CP Install Configuration file does not exist. `yum install onapp-cp-install` may not have been ran or the install script itself has not been ran.'
	exit 1;
fi

ONAPP_CONF_DIR="${ONAPP_ROOT}/interface/config"
ONAPP_CONF_FILE="${ONAPP_CONF_DIR}/on_app.yml"
DBCONF="${ONAPP_CONF_DIR}/database.yml"
DBNAME=`grep database ${DBCONF} | head -1 | awk {'print $2'} | sed "s/\"//g;s/'//g"`
SQLU=`grep username ${DBCONF} | head -1 | awk {'print $2'} | sed "s/\"//g;s/'//g"`
SQLH=`grep host ${DBCONF} | head -1 | awk {'print $2'} | sed "s/\"//g;s/'//g"`
SQLP=`grep password ${DBCONF} | head -1 | awk {'print $2'} | sed "s/'$//g;s/^'//g;s/\"$//g;s/^\"//g"`


# Database
DBDIR=`grep datadir /etc/my.cnf | cut -d'=' -f2`
DBNAME=`grep database ${DBCONF} | head -1 | awk {'print $2'} | sed "s/\"//g;s/'//g"`
SQLU=`grep username ${DBCONF} | head -1 | awk {'print $2'} | sed "s/\"//g;s/'//g"`
SQLH=`grep host ${DBCONF} | head -1 | awk {'print $2'} | sed "s/\"//g;s/'//g"`
SQLP=`grep password ${DBCONF} | head -1 | awk {'print $2'} | sed "s/'$//g;s/^'//g;s/\"$//g;s/^\"//g"`



# Run a SQL query
function runSQL()
{
    [ $# -ne 1 ] && echo "Invalid or empty SQL Query!" >&2 && exit 1
    local result=`mysql -h ${SQLH} -u ${SQLU} -p${SQLP} ${DBNAME} -Bse "${1}"`
    echo "${result}";
}

# Run the checks on all hypervisors and backup servers, display table. just for status
function runCheckHVandBS()
{
    echo -e "Label|IP Address|Ping?|SSH?|SNMP?|Version|Kernel|Distro"

    # hypervisors
    local  LABELS=`runSQL "SELECT label FROM hypervisors WHERE enabled=1 AND ip_address IS NOT NULL and ip_address NOT IN (SELECT ip_address FROM backup_servers) ORDER BY id" | sed -r -e ':a;N;$!ba;s/\n/,/g'`
    local IPADDRS=`runSQL "SELECT ip_address FROM hypervisors WHERE enabled=1 AND ip_address IS NOT NULL and ip_address NOT IN (SELECT ip_address FROM backup_servers) ORDER BY id"`
    for ip in $IPADDRS ; do
        local CURLABEL=`echo ${LABELS} | cut -d',' -f1`
        LABELS=`echo ${LABELS} | sed -r -e 's/^[^,]+,//'`
        echo -ne "${CURLABEL}|${ip}"
        checkHVBSStatus ${ip}
    done

    # backup servers
    local  LABELS=`runSQL "SELECT label from backup_servers WHERE enabled=1 AND ip_address IS NOT NULL ORDER BY id" | sed -r -e ':a;N;$!ba;s/\n/,/g'`
    local IPADDRS=`runSQL "SELECT ip_address FROM backup_servers WHERE enabled=1 AND ip_address IS NOT NULL ORDER BY id"`
    for ip in $IPADDRS ; do
        local CURLABEL=`echo ${LABELS} | cut -d',' -f1`
        LABELS=`echo ${LABELS} | sed -r -e 's/^[^,]+,//'`
        echo -ne "${CURLABEL}|${ip}"
        checkHVBSStatus ${ip}
    done
}


# Check control panel version
function cpVersion()
{
    rpm -qa onapp-cp | sed -r -e 's/onapp-cp-(.+?).noarch/\1/'
}

# Check hypervisor version
function hvVersion()
{
    cat /onapp/onapp-store-install.version
}

# Geolocate self time zone, check with configured time zone
function timeZoneCheck()
{
    local GEOTZ=`curl -s http://ip-api.com/json | sed -r -e 's/.+"timezone":"([^"]+?)".+/\1/g'`
    local CURTZ=`grep ZONE /etc/sysconfig/clock | cut -d'=' -f2 | tr -d '"'`
    ( [[ ${GEOTZ} != ${CURTZ} ]] && echo -e "${lred}Timezones don't seem the same, check that ${GEOTZ} = ${CURTZ}${nofo}" ) || echo -e "${lgreen}Timezones appear to match. ${cyan}${CURTZ}${nofo}"
}

# Check HV or BS status from control server
function checkHVBSStatus()
{
    (ping ${1} -w1 2>&1 >/dev/null && echo -ne "|YES") || echo -ne "|NO"
    (su onapp -c "ssh ${SSHOPTS} root@${1} 'exit'" 2>&1 >/dev/null && echo -ne "|YES") || echo -ne "|NO"
    (nc -z ${1} 161 2>&1 >/dev/null && echo -ne "|YES" ) || echo -ne "|NO"
    echo -ne "|"`su onapp -c "ssh ${SSHOPTS} root@${1} 'cat /onapp/onapp-store-install.version 2>/dev/null'" 2>/dev/null`
    echo -ne "|"`su onapp -c "ssh ${SSHOPTS} root@${1} 'uname -r 2>/dev/null'" 2>/dev/null`
    echo -e "|"`su onapp -c "ssh ${SSHOPTS} root@${1} 'cat /etc/redhat-release 2>/dev/null'" 2>/dev/null`
}

# CPU Family / Vendor checker. Information comes in CSV
function resourceCheck()
{
    local CPUMODEL=`grep model\ name /proc/cpuinfo -m1 | cut -d':' -f2`
    local CPUSPEED=`grep cpu\ MHz /proc/cpuinfo -m1 | cut -d':' -f2 | cut -d'.' -f1 | tr -d ' '`
    local CPUCORES=`grep cpu\ cores /proc/cpuinfo -m1 | cut -d':' -f2 | tr -d ' '`
    echo "${CPUMODEL},${CPUSPEED},${CPUCORES}"
}

# Detect if root disk is over 100GB, for static hypervisors and control panel
function rootDiskSize()
{
    # 100GB * 1024 * 1024 = 104857600 KB
    ( [ `df -l -P / | tail -1 | awk {'print $2'}` -ge 104857600 ] && echo -e "${lgreen}Disk over 100GB${nofo}" ) || echo -e "${lred}Disk under 100GB${nofo}"
}





# Control Panel Version, store for later comparison.
CP_OA_VERSION=`cpVersion`
echo "OnApp Control Panel Version ${CP_OA_VERSION}."

# Kernel and distro for control server
CP_K_VERSION=`uname -r 2>/dev/null`
CP_DISTRO=`cat /etc/redhat-release 2>/dev/null`
echo "Kernel Release ${CP_K_VERSION}"
echo "Distribution: ${CP_DISTRO}"

# Check / disk size for >=100GB
rootDiskSize

# Check time zone
timeZoneCheck

echo "Pulling table of hypervisor information..."
runCheckHVandBS | column -s '|' -t

# Check on control server for recovery and LoadBalancer templates

if [ -r ${FREEBSD_ISO_DIR}/freebsd-iso-url.list ] ; then
	TMP_ISOS=`cat ${FREEBSD_ISO_DIR}/freebsd-iso-url.list | sed -e 's#^.*/##g'`
	for ISOS in $TMP_ISOS ; do
		if [ -s ${FREEBSD_ISO_DIR}/${ISOS} ] ; then
			echo "${ISOS} is found."
		else
			echo "${ISOS} is NOT found. Please run install script or download manually."
		fi
	done
else
	echo "FreeBSD ISO URL list does not exist. Please run install script."
fi


if [ -r ${GRUB_ISO_DIR}/grub-isos-url.list ] ; then
	TMP_ISOS=`cat ${GRUB_ISO_DIR}/grub-isos-url.list | sed -e 's#^.*/##g'`
	for ISOS in $TMP_ISOS ; do
		if [ -s ${GRUB_ISO_DIR}/${ISOS} ] ; then
			echo "Grub image has been found."
		else
			echo "Grub image ${ISOS} has NOT been found. Please run install script or download manually."
		fi
	done
else
	echo "Grub ISO URL list does not exist. Please run install script."
fi


if [ -r ${RECOVERY_TEMPLATES_DIR}/recovery-templates-url.list ] ; then
	TMP_ISOS=`cat ${RECOVERY_TEMPLATES_DIR}/recovery-templates-url.list | sed -e 's#^.*/##g'`
	for ISOS in $TMP_ISOS ; do
		if [ -s ${RECOVERY_TEMPLATES_DIR}/${ISOS} ] ; then
			echo "${ISOS} is found."
		else
			echo "${ISOS} is NOT found. Please run install script or download manually."
		fi
	done
else
	echo "Recovery Template list does not exist. Please run install script."
fi


if [ -r ${WINDOWS_SMART_DRIVERS_DIR} ] ; then
	TMP_ISOS=`cat ${WINDOWS_SMART_DRIVERS_DIR}/windows-smart-drivers-url.list | sed -e 's#^.*/##g'`
	for ISOS in $TMP_ISOS ; do
		if [ -s ${WINDOWS_SMART_DRIVERS_DIR}/${ISOS} ] ; then
			echo "${ISOS} is found."
		else
			echo "${ISOS} is NOT found. Please run install script or download manually."
		fi
	done
else
	echo "Windows Smart Drivers list does not exist. Please run install script."
fi


if [ -r ${LB_TEMPLATE_DIR}/lbva-template-url.list ] ; then
	TMP_ISOS=`cat ${LB_TEMPLATE_DIR}/lbva-template-url.list | sed -e 's#^.*/##g'`
	for ISOS in $TMP_ISOS ; do 
		if [ -s ${LB_TEMPLATE_DIR}/${ISOS} ] ; then
			echo "${ISOS} is found."
		else
			echo "${ISOS} is NOT found. Please run install script or download manually."
		fi
	done
else
	echo "Load Balancer template list does not exist.  Please run install script."
fi


if [ -r ${ASVA_TEMPLATE_DIR}/asva-template-url.list ] ; then
	TMP_ISOS=`cat ${ASVA_TEMPLATE_DIR}/asva-template-url.list | sed -e 's#^.*/##g'`
	for ISOS in $TMP_ISOS ; do
		if [ -s ${ASVA_TEMPLATE_DIR}/${ISOS} ] ; then
			echo "${ISOS} is found."
		else
			echo "${ISOS} is NOT found. Please run install script or download manually."
		fi
	done
else
	echo "Application Server template list does not exist. Please run install script."
fi


if [ -r ${CDN_TEMPLATE_DIR}/cdn-template-url.list ] ; then
	TMP_ISOS=`cat ${CDN_TEMPLATE_DIR}/cdn-template-url.list | sed -r 's#^.*/##g'`
	for ISOS in $TMP_ISOS ; do
		if [ -s ${CDN_TEMPLATE_DIR}/${ISOS} ] ; then
			echo "${ISOS} is found."
		else
			echo "${ISOS} is NOT found. Please run install script or download manually."
		fi
	done
else
	echo "CDN template list does not exist. Please run install script."
fi





