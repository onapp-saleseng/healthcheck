#!/bin/bash

# Script for automatically checking integrity of OnApp installations
API_CALLS=0 ; HW_ONLY=0
while [[ $# -gt 0 ]] ; do
    key=$1
    case $key in
        -a|--api)
            API_CALLS=1
            echo "API Calls for creating VM's are enabled. Will process after all checks."
            sleep 1
            shift
        ;;
        -h|--hardware)
            HW_ONLY=1
            echo "Ending after system checks"
            sleep 1
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
PASS="${lgreen}[+]${nofo}"
FAIL="${lred}[-]${nofo}"
CHCK="${lbrown}[?]${nofo}"

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
DBDIR=`grep datadir /etc/my.cnf | cut -d'=' -f2`
SQLU=`grep username ${DBCONF} | head -1 | awk {'print $2'} | sed "s/\"//g;s/'//g"`
SQLH=`grep host ${DBCONF} | head -1 | awk {'print $2'} | sed "s/\"//g;s/'//g"`
SQLP=`grep password ${DBCONF} | head -1 | awk {'print $2'} | sed "s/'$//g;s/^'//g;s/\"$//g;s/^\"//g"`


IS_CHECK=`grep storage_enabled: /onapp/interface/config/on_app.yml | cut -d':' -f2 | tr -d ' '`
if [[ ${IS_CHECK} == 'true' ]] ; then
    echo "Integrated Storage is enabled."
    STORE_ENABLED=1
else
    echo "Integrated storage is disabled."
    STORE_ENABLED=0
fi
# Database



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
    echo -e "${brown}\n#|Label|IP Address|Ping?|SSH?|SNMP?|Version|Kernel|Distro${cyan}"
    local II=0
    # hypervisors
    local IPADDRS=`runSQL "SELECT ip_address FROM (SELECT id, label, ip_address, 1 AS row_order FROM hypervisors WHERE hypervisor_type IN ('kvm','xen') AND ip_address IS NOT NULL AND enabled=1 AND ip_address NOT IN (SELECT ip_address FROM backup_servers WHERE ip_address IS NOT NULL) UNION SELECT id, label, ip_address, 2 AS row_order FROM backup_servers WHERE ip_address IS NOT NULL AND enabled=1 ORDER BY row_order, id) AS T"`
    local  LABELS=`runSQL "SELECT label FROM (SELECT id, label, ip_address, 1 AS row_order FROM hypervisors WHERE hypervisor_type IN ('kvm','xen') AND ip_address IS NOT NULL AND enabled=1 AND ip_address NOT IN (SELECT ip_address FROM backup_servers WHERE ip_address IS NOT NULL) UNION SELECT id, label, ip_address, 2 AS row_order FROM backup_servers WHERE ip_address IS NOT NULL AND enabled=1 ORDER BY row_order, id) AS T" | sed -r -e ':a;N;$!ba;s/\n/,/g'`
    #local  LABELS=`runSQL "SELECT label FROM hypervisors WHERE enabled=1 AND ip_address IS NOT NULL and ip_address NOT IN (SELECT ip_address FROM backup_servers) ORDER BY id" | sed -r -e ':a;N;$!ba;s/\n/,/g'`
    #local IPADDRS=`runSQL "SELECT ip_address FROM hypervisors WHERE enabled=1 AND ip_address IS NOT NULL and ip_address NOT IN (SELECT ip_address FROM backup_servers) ORDER BY id"`
    for ip in $IPADDRS ; do
        II=$((${II}+1))
        local CURLABEL=`echo ${LABELS} | cut -d',' -f1`
        LABELS=`echo ${LABELS} | sed -r -e 's/^[^,]+,//'`
        echo -ne "${II}|${CURLABEL}|${ip}"
        checkHVBSStatus ${ip}
    done

    # backup servers
    #local  LABELS=`runSQL "SELECT label FROM backup_servers WHERE enabled=1 AND ip_address IS NOT NULL ORDER BY id" | sed -r -e ':a;N;$!ba;s/\n/,/g'`
    #local IPADDRS=`runSQL "SELECT ip_address FROM backup_servers WHERE enabled=1 AND ip_address IS NOT NULL ORDER BY id"`
    #for ip in $IPADDRS ; do
    #    II=$((${II}+1))
    #    local CURLABEL=`echo ${LABELS} | cut -d',' -f1`
    #    LABELS=`echo ${LABELS} | sed -r -e 's/^[^,]+,//'`
    #    echo -ne "${II}|${CURLABEL}|${ip}"
    #    checkHVBSStatus ${ip}
    #done

    echo -ne "${nofo}"
}


function checkHVConn()
{
    local IPADDRS=`runSQL "SELECT ip_address FROM (SELECT id, label, ip_address, 1 AS row_order FROM hypervisors WHERE hypervisor_type IN ('kvm','xen') AND ip_address IS NOT NULL AND enabled=1 AND ip_address NOT IN (SELECT ip_address FROM backup_servers WHERE ip_address IS NOT NULL) UNION SELECT id, label, ip_address, 2 AS row_order FROM backup_servers WHERE ip_address IS NOT NULL AND enabled=1 ORDER BY row_order, id) AS T"`
    for ip in $IPADDRS ; do
#	if [ ${1} == ${ip} ] ; then
	RETURN=`su onapp -c "ssh ${SSHOPTS} root@${1} '(ping ${ip} -w1 2>&1 >/dev/null && echo -ne \"${PASS}\") || echo -ne \"${FAIL}\"'"`
        if [[ ${RETURN} == ${FAIL} ]] ; then
            HV_CONN_FAILURE=1
        fi
        echo -ne ${RETURN}
    done
    echo
}

function checkAllHVConn()
{

    #local  LABELS=`runSQL "SELECT label FROM hypervisors WHERE enabled=1 AND ip_address IS NOT NULL and ip_address NOT IN (SELECT ip_address FROM backup_servers) ORDER BY id UNION SELECT label FROM backup_servers WHERE enabled=1 AND ip_address IS NOT NULL ORDER BY id" | sed -r -e ':a;N;$!ba;s/\n/,/g'`
    #local IPADDRS=`runSQL "SELECT ip_address FROM hypervisors WHERE enabled=1 AND ip_address IS NOT NULL ORDER BY id"`
    echo -e "\n    Checking Hypervisor Interconnectivity:\n"
    HV_CONN_FAILURE=0
    local IPADDRS=`runSQL "SELECT ip_address FROM (SELECT id, label, ip_address, 1 AS row_order FROM hypervisors WHERE hypervisor_type IN ('kvm','xen') AND ip_address IS NOT NULL AND enabled=1 AND ip_address NOT IN (SELECT ip_address FROM backup_servers WHERE ip_address IS NOT NULL) UNION SELECT id, label, ip_address, 2 AS row_order FROM backup_servers WHERE ip_address IS NOT NULL AND enabled=1 ORDER BY row_order, id) AS T"`
    II=0
    echo -n "     "
    for ip in $IPADDRS ; do
        II=$(($II+1))
        echo -n "  ${II}"
    done
    echo
    II=0
    for ip in $IPADDRS ; do
        II=$(($II+1))
        echo -n "    ${II} "
        checkHVConn $ip
    done
    echo -e "${nofo}\n"
    if [[ ${HV_CONN_FAILURE} == 1 ]] ; then
        echo -e "${FAIL} A failure was detected, see above table for ${FAIL}, #'s are in system information table further above."
    else
        echo -e "${PASS} All hypervisors can ping each other."
    fi
}

function checkISConn()
{
    #local IPADDRS=`runSQL "SELECT ip_address FROM hypervisors WHERE enabled=1 AND ip_address IS NOT NULL ORDER BY id"`
    #local HOSTIDS=`runSQL "SELECT host_id FROM hypervisors WHERE enabled=1 AND ip_address IS NOT NULL ORDER BY id"`
    echo "    Checking storage networking:"
    echo
    local IPADDRS=`runSQL "SELECT ip_address FROM (SELECT id, label, ip_address, 1 AS row_order FROM hypervisors WHERE hypervisor_type IN ('kvm','xen') AND ip_address IS NOT NULL AND host_id IS NOT NULL AND enabled=1 AND ip_address NOT IN (SELECT ip_address FROM backup_servers WHERE ip_address IS NOT NULL) UNION SELECT id, host_id, ip_address, 2 AS row_order FROM hypervisors WHERE ip_address IS NOT NULL AND host_id IS NOT NULL AND enabled=1 AND ip_address IN (SELECT ip_address FROM backup_servers) ORDER BY row_order, id) AS T"`
    local HOSTIDS=`runSQL "SELECT host_id FROM (SELECT id, host_id, ip_address, 1 AS row_order FROM hypervisors WHERE hypervisor_type IN ('kvm','xen') AND ip_address IS NOT NULL AND host_id IS NOT NULL AND enabled=1 AND ip_address NOT IN (SELECT ip_address FROM backup_servers WHERE ip_address IS NOT NULL) UNION SELECT id, host_id, ip_address, 2 AS row_order FROM hypervisors WHERE ip_address IS NOT NULL AND host_id IS NOT NULL AND enabled=1 AND ip_address IN (SELECT ip_address FROM backup_servers) ORDER BY row_order, id) AS T"`
    local LABELS=`runSQL "SELECT label FROM (SELECT id, label, ip_address, 1 AS row_order FROM hypervisors WHERE hypervisor_type IN ('kvm','xen') AND ip_address IS NOT NULL AND host_id IS NOT NULL AND enabled=1 AND ip_address NOT IN (SELECT ip_address FROM backup_servers WHERE ip_address IS NOT NULL) UNION SELECT id, label, ip_address, 2 AS row_order FROM hypervisors WHERE ip_address IS NOT NULL AND host_id IS NOT NULL AND enabled=1 AND ip_address IN (SELECT ip_address FROM backup_servers) ORDER BY row_order, id) AS T" | sed -r -e ':a;N;$!ba;s/\n/,/g'`
    II=0
    for ip in $IPADDRS ; do
        II=$(($II+1))
        local CURLABEL=`echo ${LABELS} | cut -d',' -f1`
        LABELS=`echo ${LABELS} | sed -r -e 's/^[^,]+,//'`
        echo -e "  ${II} - ${CURLABEL} @ ${ip}"
    done
    echo -n "     "
    II=0
    for ip in $IPADDRS ; do
        II=$(($II+1))
        echo -ne "  ${II}"
    done
    echo
    II=0
    IS_CONN_FAILURE=0
    FAIL_OUTPUT=""
    for ip in $IPADDRS ; do
        II=$(($II+1))
        echo -ne "    ${II} "
        for hosts in $HOSTIDS ; do
            RETURN=`su onapp -c "ssh ${SSHOPTS} root@${ip} '(ping 10.200.${hosts}.254 -w1 2>&1 >/dev/null && echo -ne \"${PASS}\") || echo -ne \"${FAIL}\"'"`
            if [[ ${RETURN} == ${FAIL} ]] ; then
                IS_CONN_FAILURE=1
                FAIL_OUTPUT="${FAIL_OUTPUT},${ip} cannot ping 10.200.${hosts}.254"
            fi
            echo -ne ${RETURN}
        done
        echo
    done
    echo -e ${nofo}
    if [[ ${IS_CONN_FAILURE} == 1 ]] ; then
        echo -e "${FAIL} Not all hypervisors are able to ping each other over the storage network."
        echo -e "${FAIL_OUTPUT}"
    else
        echo -e "${PASS} All hypervisors can ping each other over the storage network."
    fi
    echo
}


function checkNetZones()
{
    local NJIDS=`runSQL "SELECT network_id FROM networking_network_joins WHERE target_join_id=${1}"`
    if [ "x${NJIDS}" == "x" ] ; then echo -e "${FAIL} No Networks Joined!${nofo}" ; fi
    for CURNID in ${NJIDS} ; do
        echo -e "${PASS} Network Join:${green} " `runSQL "SELECT label FROM networking_networks WHERE id=${CURNID}"` "${nofo}"
    done
}

function checkDataZones()
{
    local DZJIDS=`runSQL "SELECT data_store_id FROM data_store_joins WHERE target_join_id=${1}"`
    if [ "x${DZJIDS}" == "x" ] ; then echo -e "${FAIL} No Data Stores Joined!${nofo}" ; fi
    for CURDID in ${DZJIDS} ; do
        echo -e "${PASS} Data Store Join:${green} " `runSQL "SELECT label FROM data_stores WHERE id=${CURDID}"` "${nofo}"
    done
}

function checkBackupJoin()
{
    local BSJIDS=`runSQL "SELECT backup_server_id FROM backup_server_joins WHERE target_join_id=${1}"`
    if [ "x${BSJIDS}" == "x" ] ; then echo -e "${CHCK} No Backup Servers Joined${nofo}" ; fi
    for CURBID in ${BSJIDS} ; do
        echo -e "${PASS} Backup Server Join: ${green}" `runSQL "SELECT label FROM backup_servers WHERE id=${CURBID}"` "${nofo}"
    done
}

function checkComputeZones()
{
    echo '    Ensuring Compute Zones have proper joins...'
    local CZ=`runSQL "SELECT id FROM packs WHERE type='HypervisorGroup'"`
    for CURID in ${CZ} ; do
        echo -e "--- Checking Compute Zone:${cyan}" `runSQL "SELECT label FROM packs WHERE id=${CURID}"` "${nofo}"
        checkNetZones ${CURID}
        checkDataZones ${CURID}
        checkBackupJoin ${CURID}
        echo '    -------------------'
    done
}

function createDestroyVM()
{
  # API Calls for creating a VM and then destroying it if possible.
    local TEMPLATE_IDS=`runSQL "SELECT t.id FROM template_groups AS tg JOIN relation_group_templates AS tjn ON image_template_group_id=tg.id JOIN templates t ON t.id=tjn.template_id WHERE tg.system_group=0;"`
    if [[ `echo -n ${TEMPLATE_IDS} | wc -m` -eq 1 ]] ; then
        echo -e "    Found one template ID ${TEMPLATE_IDS}, Label: "`runSQL "SELECT label FROM templates WHERE id=${TEMPLATE_IDS}"`
        TEMPLATE_ID=${TEMPLATE_IDS}
    else
        echo -e "${CHCK} Found multiple non-system templates. Which one should I use?"
        for CURID in $TEMPLATE_IDS ; do
            echo "    Template ID: ${CURID} , Template Label: "`runSQL "SELECT label FROM templates WHERE id=${CURID}"`
        done
        echo -ne "\n${CHCK} Provide template ID: "
        read TEMPLATE_ID
        TEMPLATE_ID=`echo ${TEMPLATE_ID} | tr -dc '0-9'`
    fi
    if [ "x${TEMPLATE_ID}" == "x" ] ; then echo -e "${FAIL} Template ID is BLANK! Exiting..." && exit 1 ; fi
    local MIN_RAM="`runSQL "SELECT min_memory_size FROM templates WHERE id=${TEMPLATE_ID}"`"
    local MIN_P_DISK="`runSQL "SELECT min_disk_size FROM templates WHERE id=${TEMPLATE_ID}"`"
    local XML_REQ="<virtual_machine><template_id>${TEMPLATE_ID}</template_id><label>QATest</label><hostname>qatest</hostname><cpus>1</cpus><cpu_shares>100</cpu_shares><memory>${MIN_RAM}</memory><primary_disk_size>${MIN_P_DISK}</primary_disk_size><required_ip_address_assignment>1</required_ip_address_assignment><required_virtual_machine_build>1</required_virtual_machine_build><required_virtual_machine_startup>1</required_virtual_machine_startup></virtual_machine>"
    local QUERY=`curl -s -i -X POST -H 'Accept: application/xml' -H 'Content-type: application/xml' -u ${1}:${2} -d "${XML_REQ}" --url http://localhost/virtual_machines.xml`
    local result=$QUERY
    local VM_IDENT=`echo $result | sed -r -e 's/> </>\n</g' | grep -e '<identifier>' -m1 | sed -r -e 's/.+?>([a-z]+)<.+?/\1/'`
    local VM_ID=`echo $result | sed -r -e 's/> </>\n</g' | grep -e '<id type' -m1 | sed -r -e 's/.+?>([0-9]+)<.+?/\1/'`
    sleep 5
    if [[ "x${VM_ID}" == "x" ]] ; then echo -e "${FAIL} An issue occurred creating the virtual machine. Please attempt manually or resolve any previous issues." && exit 1 ; fi
    VM_ONLINE=0
    echo "    Watching for virtual machine (ID ${VM_ID}) to come online..."
    COUNT=0
    while [ ${VM_ONLINE} -eq 0 ] ; do
        # local result=`runSQL "SELECT booted FROM virtual_machines WHERE id=${VM_ID}" | tr -dc '0-9'`
        local result=`curl -s -i -X GET -H 'Accept: application/xml' -H 'Content-type: application/xml' -u ${1}:${2} --url http://localhost/virtual_machines/${VM_ID}/status.xml | sed -r -e 's/> </>\n</g'`
        local VM_STATUS=`echo ${result} | grep state | sed -r -e 's/.+?state>([a-z]+)<.+?/\1/g'`
        if [[ "${VM_STATUS}" == "delivered" ]] ; then echo -e "${PASS} Virtual machine is marked as ${green}booted${nofo}." ; VM_ONLINE=1 ; fi
        let "COUNT += 1"
        if [ ${COUNT} -gt 9 ] ; then
            if [[ "${VM_STATUS}" == "failed" ]] ; then echo -e "${FAIL} Virtual machine build has ${red}failed.${nofo} Please recheck template and correct setup" ; VM_ONLINE=1; fi
        fi
        sleep 5
    done

    echo "    Destroying virtual machine."
    sleep 5

    local QUERY="curl -s -i -X DELETE -u ${1}:${2} http://localhost/virtual_machines/${VM_ID}.xml?convert_last_backup=0&destroy_all_backups=1"
    local result=`$QUERY`

    echo "    Watching for virtual machine to be destroyed"
    COUNT=0
    while [ ${VM_ONLINE} -eq 1 ] ; do
        local result=`runSQL "SELECT deleted_at FROM virtual_machines WHERE id=${VM_ID}"`
        #local result=`curl -s -i -X GET -H 'Accept: application/xml' -H 'Content-type: application/xml' -u ${1}:${2} --url http://localhost/virtual_machines/${VM_ID}/status.xml | sed -r -e 's/> </>\n</g'`
        #local VM_STATUS=`echo ${result} | grep state | sed -r -e 's/.+?state>([a-z]+)<.+?/\1/g'`
        #COUNT=${COUNT}+1
        let "COUNT += 1"
        if [[ ${result} != "NULL" ]] ; then
            echo -e "${PASS} Virtual machine appears to have been destroyed."
            VM_ONLINE=2
        #else
            #if [ ${COUNT} -gt 19 ] ; then
            #    echo "Checking for failure..."
                #Magic for detecting failure
            #fi
        fi
        sleep 2
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
    if [ -f /onapp/onapp-store-install.version ] ; then
        cat /onapp/onapp-store-install.version
    else if [ -f /onapp/onapp-hv-tools.version ] ; then
            cat /onapp/onapp-hv-tools.version
        else if [ -f /onappstore/package-version.txt ] ; then
                grep Version /onappstore/package-version.txt
            else
                echo 'echo a'
            fi
        fi
    fi
}

# Geolocate self time zone, check with configured time zone
function timeZoneCheck()
{
    local GEOTZ=`curl -s http://ip-api.com/json | sed -r -e 's/.+"timezone":"([^"]+?)".+/\1/g'`
    local CURTZ=`timedatectl | grep Time\ zone | awk {'print $3'}`
    ( [[ ${GEOTZ} != ${CURTZ} ]] && echo -e "${CHCK} Timezones don't seem the same, check that ${GEOTZ} = ${CURTZ}" ) \
	 || echo -e "${PASS} Timezones appear to match: ${CURTZ}${nofo}"
}

# Check HV or BS status from control server
function checkHVBSStatus()
{
    (ping ${1} -w1 2>&1 >/dev/null && echo -ne "|YES") || echo -ne "|NO"
    (su onapp -c "ssh ${SSHOPTS} root@${1} 'exit'" 2>&1 >/dev/null && echo -ne "|YES") || echo -ne "|NO"
    (nc ${1} 161  2>&1 >/dev/null </dev/null && echo -ne "|YES" ) || echo -ne "|NO"
    echo -ne "|"`su onapp -c "ssh ${SSHOPTS} root@${1} '$(typeset -f hvVersion);hvVersion'" | sed -r -e 's/.+: ([0-9]\.[0-9]).+/\1/'`
    echo -ne "|"`su onapp -c "ssh ${SSHOPTS} root@${1} 'uname -r 2>/dev/null'" 2>/dev/null`
    echo -e "|"`su onapp -c "ssh ${SSHOPTS} root@${1} 'cat /etc/redhat-release 2>/dev/null'" 2>/dev/null`
}

# CPU Family / Vendor checker. Information comes in CSV
function resourceCheck()
{
    local CPUMODEL=`grep model\ name /proc/cpuinfo -m1 | cut -d':' -f2 | sed -r -e 's/^ //;s/ $//'`
    local CPUSPEED=`grep cpu\ MHz /proc/cpuinfo -m1 | cut -d':' -f2 | cut -d'.' -f1 | tr -d ' '`
    local CPUCORES=`grep cpu\ cores /proc/cpuinfo -m1 | cut -d':' -f2 | tr -d ' '`
    echo "${CPUMODEL},${CPUSPEED},${CPUCORES}"
}

function checkHVHW()
{
    echo -e "HV,CPU Model,CPU MHz,CPU Cores${cyan}"
    local IPADDRS=`runSQL "SELECT ip_address FROM (SELECT id, label, ip_address, 1 AS row_order FROM hypervisors WHERE hypervisor_type IN ('kvm','xen') AND ip_address IS NOT NULL AND enabled=1 AND ip_address NOT IN (SELECT ip_address FROM backup_servers WHERE ip_address IS NOT NULL) UNION SELECT id, label, ip_address, 2 AS row_order FROM backup_servers WHERE ip_address IS NOT NULL AND enabled=1 ORDER BY row_order, id) AS T"`
    local  LABELS=`runSQL "SELECT label FROM (SELECT id, label, ip_address, 1 AS row_order FROM hypervisors WHERE hypervisor_type IN ('kvm','xen') AND ip_address IS NOT NULL AND enabled=1 AND ip_address NOT IN (SELECT ip_address FROM backup_servers WHERE ip_address IS NOT NULL) UNION SELECT id, label, ip_address, 2 AS row_order FROM backup_servers WHERE ip_address IS NOT NULL AND enabled=1 ORDER BY row_order, id) AS T" | sed -r -e ':a;N;$!ba;s/\n/,/g'`
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
    ( [ `df -l -P -BG / | tail -1 | awk {'print $2'} | tr -d G` -ge 100 ] && echo -e "${PASS} Disk over 100GB" ) || echo -e "${FAIL} Disk under 100GB"
}



###############################################
###############################################
###############################################
###############################################
##### Action starts here, functions above #####
###############################################
###############################################
###############################################
###############################################

echo "-------------------------------------"
echo -e "\033[0;37;44mOn\033[0;34;47mApp${nofo} Enterprise Quality Check Script"
echo "-------------------------------------"
echo
echo "    Control Server System Information:"

# Control Panel Version, store for later comparison.
CP_OA_VERSION=`cpVersion`
echo -e "    OnApp Control Panel Version ${cyan}${CP_OA_VERSION}${nofo}."

# Kernel and distro for control server
CP_K_VERSION=`uname -r 2>/dev/null`
CP_DISTRO=`cat /etc/redhat-release 2>/dev/null`
echo -e "    Kernel Release ${cyan}${CP_K_VERSION}${nofo}"
echo -e "    Distribution: ${cyan}${CP_DISTRO}${nofo}"
echo -e "    CPU Model:${cyan} `grep model\ name /proc/cpuinfo -m1 | cut -d':' -f2 | sed -r -e 's/^ //;s/ $//'`${nofo}"
echo -e "    CPU Speed:${cyan} `grep cpu\ MHz /proc/cpuinfo -m1 | cut -d':' -f2 | cut -d'.' -f1 | tr -d ' '`${nofo} MHz"
CP_CPU_CORES=`grep cpu\ cores /proc/cpuinfo -m1 | cut -d':' -f2 | tr -d ' '`
if [[ ${CP_CPU_CORES} -lt 8 ]] ; then
    echo -e "${CHCK} CPU Cores:${lbrown} ${CP_CPU_CORES}${nofo} (recommended 8)"
else
    echo -e "${PASS} CPU Cores:${cyan}"
fi
CP_MEMORY=`free -m | grep Mem | awk {'print $2'}`
if [[ ${CP_MEMORY} -lt 16000 ]] ; then
    echo -e "${CHCK} Memory: ${lbrown}${CP_MEMORY}${nofo} (recommended 16GB)"
else
    echo -e "${PASS} Memory: ${cyan}${CP_MEMORY}${nofo} MB"
fi
rootDiskSize
# Check on control server for recovery and LoadBalancer templates
TEMP_FAIL=0
if [ -r ${FREEBSD_ISO_DIR}/freebsd-iso-url.list ] ; then
	TMP_ISOS=`cat ${FREEBSD_ISO_DIR}/freebsd-iso-url.list | sed -e 's#^.*/##g'`
	for ISOS in $TMP_ISOS ; do
		if [ -s ${FREEBSD_ISO_DIR}/${ISOS} ] ; then
			#echo -e "${green}${ISOS} is found."
			:
		else
			echo -e "\t${lred}FreeBSD ${ISOS} is NOT found.${nofo}"
			TEMP_FAIL=$TEMP_FAIL+1
		fi
	done
else
	echo -e "${red}FreeBSD ISO URL list does not exist. Please run install script.${nofo}"
	TEMP_FAIL=$TEMP_FAIL+1
fi


if [ -r ${GRUB_ISO_DIR}/grub-isos-url.list ] ; then
	TMP_ISOS=`cat ${GRUB_ISO_DIR}/grub-isos-url.list | sed -e 's#^.*/##g'`
	for ISOS in $TMP_ISOS ; do
		if [ -s ${GRUB_ISO_DIR}/${ISOS} ] ; then
			#echo -e "${green}Grub image ${ISOS} has been found."
			:
		else
			echo -e "\t${lred}Grub image ${ISOS} has NOT been found.${nofo}"
			TEMP_FAIL=$TEMP_FAIL+1
		fi
	done
else
	echo -e "${red}Grub ISO URL list does not exist.${nofo}"
	TEMP_FAIL=$TEMP_FAIL+1
fi


if [ -r ${RECOVERY_TEMPLATES_DIR}/recovery-templates-url.list ] ; then
	TMP_ISOS=`cat ${RECOVERY_TEMPLATES_DIR}/recovery-templates-url.list | sed -e 's#^.*/##g'`
	for ISOS in $TMP_ISOS ; do
		if [ -s ${RECOVERY_TEMPLATES_DIR}/${ISOS} ] ; then
			#echo -e "${green}${ISOS} is found."
			:
		else
			echo -e "\t${lred}Recovery template ${ISOS} is NOT found.${nofo}"
			TEMP_FAIL=$TEMP_FAIL+1
		fi
	done
else
	echo -e "${red}Recovery Template list does not exist.${nofo}"
	TEMP_FAIL=$TEMP_FAIL+1
fi


if [ -r ${WINDOWS_SMART_DRIVERS_DIR} ] ; then
	TMP_ISOS=`cat ${WINDOWS_SMART_DRIVERS_DIR}/windows-smart-drivers-url.list | sed -e 's#^.*/##g'`
	for ISOS in $TMP_ISOS ; do
		if [ -s ${WINDOWS_SMART_DRIVERS_DIR}/${ISOS} ] ; then
			#echo -e "${green}${ISOS} is found."
			:
		else
			echo -e "\t${lred}Windows driver image ${ISOS} is NOT found.${nofo}"
			TEMP_FAIL=$TEMP_FAIL+1
		fi
	done
else
	echo -e "${red}Windows Smart Drivers list does not exist. Please run install script."
	TEMP_FAIL=$TEMP_FAIL+1
fi


if [ -r ${LB_TEMPLATE_DIR}/lbva-template-url.list ] ; then
	TMP_ISOS=`cat ${LB_TEMPLATE_DIR}/lbva-template-url.list | sed -e 's#^.*/##g'`
	for ISOS in $TMP_ISOS ; do
		if [ -s ${LB_TEMPLATE_DIR}/${ISOS} ] ; then
			#echo -e "${green}${ISOS} is found."
			:
		else
			echo -e "\t${lred}Load Balancer template ${ISOS} is NOT found.${nofo}"
			TEMP_FAIL=$TEMP_FAIL+1
		fi
	done
else
	echo -e "${red}Load Balancer template list does not exist.  Please run install script.${nofo}"
	TEMP_FAIL=$TEMP_FAIL+1
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
			#echo -e "${green}CDN Template ${ISOS} is found."
			:
		else
			echo -e "\t${lred}CDN Template ${ISOS} is NOT found."
			TEMP_FAIL=$TEMP_FAIL+1
		fi
	done
else
	echo -e "${red}CDN template list does not exist. Please run install script.${nofo}"
	TEMP_FAIL=$TEMP_FAIL+1
fi

if [ $TEMP_FAIL -eq 0 ] ; then
	echo -e "${PASS} All system templates are detectable."
else
	echo -e "${CHCK} There are $TEMP_FAIL template fail checks. See above for missing templates."
fi

echo -ne "${nofo}"


# Check time zone
timeZoneCheck
echo
echo '------------------------------------------'
echo "Pulling table of hypervisor information..."
runCheckHVandBS | column -s '|' -t

echo -e "Checking hardware...${brown}\n"
checkHVHW | column -s ',' -t -c4
echo -e "${nofo}"

if [ ${HW_ONLY} -eq 1 ] ; then
    exit 0
fi

#check HV interconnectivity
checkAllHVConn
[ $STORE_ENABLED -eq 1 ] && checkISConn || echo 'Skipping storage check.'

checkComputeZones



if [ ${API_CALLS} -eq 1 ] ; then
  echo '----------------------------'
  echo
  echo -e "${CHCK} API Calls are enabled but require a username and password."
  echo -ne "${CHCK} Please provide administrator username: "
  read API_USER
  echo -ne "${CHCK} Please provide password for this user: "
  read -s API_PASS
  echo
  createDestroyVM ${API_USER} ${API_PASS}
fi
