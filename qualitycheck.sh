#!/bin/bash

# Script for automatically checking integrity of OnApp installations
API_CALLS=0
while [[ $# -gt 1 ]] ; do
    key=$1
    case $key in
        -a|--api)
        API_CALLS=1
        shift
        ;;
    esac
    shift
done

# Colors
nofo='\e[0m'      #Regular
bold='\e[1m'      #Regular bold
grey='\e[30m'     #Grey
red='\e[31m'      #Red
green='\e[32m'    #Green
brown='\e[33m'    #Brown
blue='\e[34m'     #Blue
purp='\e[35m'     #Purple
cyan='\e[36m'     #Cyan
white='\e[37m'    #White
whiteb='\e[1;37m' #White Bold
lgrey='\e[1;30m'  #Light Grey
lred='\e[1;31m'   #Light Red
lgreen='\e[1;32m' #Light Green
lbrown='\e[1;33m' #Light Brown
lblue='\e[1;34m'  #Light Blue
lpurp='\e[1;35m'  #Light Purple
lcyan='\e[1;36m'  #Light Cyan
###

# Check for and include the install config file
CFG='/onapp/onapp-cp-install/onapp-cp-install.conf'

if [ -r $CFG ] ; then
	. $CFG
else
	echo -e "\n${red}CP Install Configuration file does not exist. \`yum install onapp-cp-install\` may not have been ran or the install script itself has not been ran.${nofo}"
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
    [ $# -ne 1 ] && echo -e "${red}Invalid or empty SQL Query!${nofo}" >&2 && exit 1
    local result=`mysql -h ${SQLH} -u ${SQLU} -p${SQLP} ${DBNAME} -Bse "${1}"`
    echo "${result}";
}

# Run the checks on all hypervisors and backup servers, display table. just for status
function runCheckHVandBS()
{
    echo -e "${lbrown}\nLabel|IP Address|Ping?|SSH?|SNMP?|Version|Kernel|Distro${cyan}"

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

    echo -ne "${nofo}"
}


function checkHVConn()
{
    local IPADDRS=`runSQL "SELECT ip_address FROM hypervisors WHERE enabled=1 AND ip_address IS NOT NULL ORDER BY id"`
    for ip in $IPADDRS ; do
	if [ ${1} == ${ip} ] ; then
            continue
        fi
	su onapp -c "ssh ${SSHOPTS} root@${1} '(ping ${ip} -w1 2>&1 >/dev/null && echo -e \"${green}$1 can ping $ip\") || echo -e \"${lred}$1 Cannot ping $ip\"'"
    done
}

function checkAllHVConn()
{
    local IPADDRS=`runSQL "SELECT ip_address FROM hypervisors WHERE enabled=1 AND ip_address IS NOT NULL ORDER BY id"`
    for ip in $IPADDRS ; do
        checkHVConn $ip
    done
    echo -e "${nofo}"
}

checkISConn()
{
    local IPADDRS=`runSQL "SELECT ip_address FROM hypervisors WHERE enabled=1 AND ip_address IS NOT NULL ORDER BY id"`
    local HOSTIDS=`runSQL "SELECT host_id FROM hypervisors WHERE enabled=1 AND ip_address IS NOT NULL ORDER BY id"`
    for ip in $IPADDRS ; do
        for hosts in $HOSTIDS ; do
            su onapp -c "ssh ${SSHOPTS} root@${ip} '(ping 10.200.${hosts}.254 -w1 2>&1 >/dev/null && echo -e \"${green}${ip} can ping 10.200.${hosts}.254\") || echo -e \"${lred}${ip} Cannot ping 10.200.${hosts}.254\"'"
        done
    done
    echo -e ${nofo}
}


checkNetZones()
{
    local NJIDS=`runSQL "SELECT network_id FROM networking_network_joins WHERE target_join_id=${1}"`
    if [ "x${NJIDS}" == "x" ] ; then echo -e "${lred}No Networks Joined!${nofo}" ; fi
    for CURNID in ${NJIDS} ; do
        echo -e "Network Join:${green} " `runSQL "SELECT label FROM networking_networks WHERE id=${CURNID}"` "${nofo}"
    done
}

checkDataZones()
{
    local DZJIDS=`runSQL "SELECT data_store_id FROM data_store_joins WHERE target_join_id=${1}"`
    if [ "x${DZJIDS}" == "x" ] ; then echo -e "${lred}No Data Stores Joines!${nofo}" ; fi
    for CURDID in ${DZJIDS} ; do
        echo -e "Data Store Join:${green} " `runSQL "SELECT label FROM data_stores WHERE id=${CURDID}"` "${nofo}"
    done
}

checkBackupJoin()
{
    local BSJIDS=`runSQL "SELECT backup_server_id FROM backup_server_joins WHERE target_join_id=${1}"`
    if [ "x${BSJIDS}" == "x" ] ; then echo -e "${purp}No Backup Servers Joined${nofo}" ; fi
    for CURBID in ${BSJIDS} ; do
        echo -e "Backup Server Join: ${green}" `runSQL "SELECT label FROM backup_servers WHERE id=${CURBID}"` "${nofo}"
    done
}

checkComputeZones()
{
    local CZ=`runSQL "SELECT id FROM packs WHERE type='HypervisorGroup'"`
    for CURID in ${CZ} ; do
        echo -e "Checking Compute Zone:${cyan}" `runSQL "SELECT label FROM packs WHERE id=${CURID}"` "${nofo}"
        checkNetZones ${CURID}
        checkDataZones ${CURID}
        checkBackupJoin ${CURID}
    done
}

#createDestroyVM()
#{
  # API Calls for creating a VM and then destroying it if possible.
#}

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
    local CURTZ=`timedatectl | grep Time\ zone | awk {'print $3'}`
    ( [[ ${GEOTZ} != ${CURTZ} ]] && echo -e "${purp}Timezones don't seem the same, check that ${GEOTZ} = ${CURTZ}${nofo}" ) || echo -e "${lgreen}Timezones appear to match. ${cyan}${CURTZ}${nofo}"
}

# Check HV or BS status from control server
function checkHVBSStatus()
{
    (ping ${1} -w1 2>&1 >/dev/null && echo -ne "|YES") || echo -ne "|NO"
    (su onapp -c "ssh ${SSHOPTS} root@${1} 'exit'" 2>&1 >/dev/null && echo -ne "|YES") || echo -ne "|NO"
    (nc -c '' ${1} 161 2>&1 >/dev/null && echo -ne "|YES" ) || echo -ne "|NO"
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

function checkHVHW()
{
    echo -e "HV,CPU Model,CPU MHz,CPU Cores${cyan}"
    local  LABELS=`runSQL "SELECT label FROM hypervisors WHERE enabled=1 AND ip_address IS NOT NULL ORDER BY id" | sed -r -e ':a;N;$!ba;s/\n/,/g'`
    local IPADDRS=`runSQL "SELECT ip_address FROM hypervisors WHERE enabled=1 AND ip_address IS NOT NULL ORDER BY id"`
    for ip in $IPADDRS ; do
        local CURLABEL=`echo ${LABELS} | cut -d',' -f1`
        LABELS=`echo ${LABELS} | sed -r -e 's/^[^,]+,//'`
        echo -ne "${CURLABEL}"
        echo -ne ","`su onapp -c 'grep model\ name /proc/cpuinfo -m1 | cut -d":" -f2'` 
        echo -ne ","`su onapp -c 'grep cpu\ MHz /proc/cpuinfo -m1 | cut -d":" -f2 | cut -d"." -f1 | tr -d " "'` 
        echo -e ","`su onapp -c 'grep cpu\ cores /proc/cpuinfo -m1 | cut -d":" -f2 | tr -d " "'`
    done
}

# Detect if root disk is over 100GB, for static hypervisors and control panel
function rootDiskSize()
{
    # 100GB * 1024 * 1024 = 104857600 KB
    ( [ `df -l -P -BG / | tail -1 | awk {'print $2'} | tr -d G` -ge 100 ] && echo -e "${lgreen}Disk over 100GB${nofo}" ) || echo -e "${lred}Disk under 100GB${nofo}"
}



echo "-------------------------------------"
echo "OnApp Enterprise Quality Check Script"
echo "-------------------------------------"
echo 

# Control Panel Version, store for later comparison.
CP_OA_VERSION=`cpVersion`
echo -e "OnApp Control Panel Version ${lbrown}${CP_OA_VERSION}${nofo}."

# Kernel and distro for control server
CP_K_VERSION=`uname -r 2>/dev/null`
CP_DISTRO=`cat /etc/redhat-release 2>/dev/null`
echo -e "Kernel Release ${lbrown}${CP_K_VERSION}${nofo}"
echo -e "Distribution: ${lbrown}${CP_DISTRO}${nofo}"

CPUTABLE="\nCPU Model,CPU MHz,CPU Cores\n`resourceCheck`"
echo -e "${CPUTABLE}" | column -s ',' -t

# Check / disk size for >=100GB
rootDiskSize

# Check time zone
timeZoneCheck

sleep 1.0
# Check on control server for recovery and LoadBalancer templates

if [ -r ${FREEBSD_ISO_DIR}/freebsd-iso-url.list ] ; then
	TMP_ISOS=`cat ${FREEBSD_ISO_DIR}/freebsd-iso-url.list | sed -e 's#^.*/##g'`
	for ISOS in $TMP_ISOS ; do
		if [ -s ${FREEBSD_ISO_DIR}/${ISOS} ] ; then
			echo -e "${green}${ISOS} is found."
		else
			echo -e "${lred}${ISOS} is NOT found. Please run install script or download manually."
		fi
	done
else
	echo -e "${red}FreeBSD ISO URL list does not exist. Please run install script."
fi


if [ -r ${GRUB_ISO_DIR}/grub-isos-url.list ] ; then
	TMP_ISOS=`cat ${GRUB_ISO_DIR}/grub-isos-url.list | sed -e 's#^.*/##g'`
	for ISOS in $TMP_ISOS ; do
		if [ -s ${GRUB_ISO_DIR}/${ISOS} ] ; then
			echo -e "${green}Grub image ${ISOS} has been found."
		else
			echo -e "${lred}Grub image ${ISOS} has NOT been found. Please run install script or download manually."
		fi
	done
else
	echo -e "${red}Grub ISO URL list does not exist. Please run install script."
fi


if [ -r ${RECOVERY_TEMPLATES_DIR}/recovery-templates-url.list ] ; then
	TMP_ISOS=`cat ${RECOVERY_TEMPLATES_DIR}/recovery-templates-url.list | sed -e 's#^.*/##g'`
	for ISOS in $TMP_ISOS ; do
		if [ -s ${RECOVERY_TEMPLATES_DIR}/${ISOS} ] ; then
			echo -e "${green}${ISOS} is found."
		else
			echo -e "${lred}${ISOS} is NOT found. Please run install script or download manually."
		fi
	done
else
	echo -e "${red}Recovery Template list does not exist. Please run install script."
fi


if [ -r ${WINDOWS_SMART_DRIVERS_DIR} ] ; then
	TMP_ISOS=`cat ${WINDOWS_SMART_DRIVERS_DIR}/windows-smart-drivers-url.list | sed -e 's#^.*/##g'`
	for ISOS in $TMP_ISOS ; do
		if [ -s ${WINDOWS_SMART_DRIVERS_DIR}/${ISOS} ] ; then
			echo -e "${green}${ISOS} is found."
		else
			echo -e "${lred}${ISOS} is NOT found. Please run install script or download manually."
		fi
	done
else
	echo -e "${red}Windows Smart Drivers list does not exist. Please run install script."
fi


if [ -r ${LB_TEMPLATE_DIR}/lbva-template-url.list ] ; then
	TMP_ISOS=`cat ${LB_TEMPLATE_DIR}/lbva-template-url.list | sed -e 's#^.*/##g'`
	for ISOS in $TMP_ISOS ; do 
		if [ -s ${LB_TEMPLATE_DIR}/${ISOS} ] ; then
			echo -e "${green}${ISOS} is found."
		else
			echo -e "${lred}${ISOS} is NOT found. Please run install script or download manually."
		fi
	done
else
	echo -e "${red}Load Balancer template list does not exist.  Please run install script."
fi


# if [ -r ${ASVA_TEMPLATE_DIR}/asva-template-url.list ] ; then
	# TMP_ISOS=`cat ${ASVA_TEMPLATE_DIR}/asva-template-url.list | sed -e 's#^.*/##g'`
	# for ISOS in $TMP_ISOS ; do
		# if [ -s ${ASVA_TEMPLATE_DIR}/${ISOS} ] ; then
			# echo "${ISOS} is found."
		# else
			# echo "${ISOS} is NOT found. Please run install script or download manually."
		# fi
	# done
# else
	# echo "Application Server template list does not exist. Please run install script."
# fi


if [ -r ${CDN_TEMPLATE_DIR}/cdn-template-url.list ] ; then
	TMP_ISOS=`cat ${CDN_TEMPLATE_DIR}/cdn-template-url.list | sed -r 's#^.*/##g'`
	for ISOS in $TMP_ISOS ; do
		if [ -s ${CDN_TEMPLATE_DIR}/${ISOS} ] ; then
			echo -e "${green}CDN Template ${ISOS} is found."
		else
			echo -e "${lred}CDN Template ${ISOS} is NOT found. Please run install script or download manually."
		fi
	done
else
	echo -e "${red}CDN template list does not exist. Please run install script."
fi

echo -e "${nofo}"



echo "Pulling table of hypervisor information..."
runCheckHVandBS | column -s '|' -t

echo -e "Checking hardware...${lbrown}"
checkHVHW | column -s ',' -t -c4
echo -e "${nofo}"


#check HV interconnectivity
checkAllHVConn
checkISConn

checkComputeZones



if [ ${API_CALLS} -eq 1 ] ; then
  echo -n "Please provide administrator username: "
  read API_USER
  echo -n "Please provide password for this user: "
  read -s API_PASS

  createDestroyVM ${API_USER} ${API_PASS}
fi
