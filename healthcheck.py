#!/usr/bin/python
import os
import ast
import ssl
import sys
import json
import shlex
import base64
import socket
import random
import httplib
import inspect
import argparse
import datetime
import subprocess
# from subprocess import call, Popen
from copy import copy
from urllib2 import Request, urlopen, URLError, build_opener, HTTPHandler, HTTPError

ONAPP_ROOT = '/onapp'
ONAPP_CONF_DIR="{0}/interface/config".format(ONAPP_ROOT);
ONAPP_CONF_FILE="{0}/on_app.yml".format(ONAPP_CONF_DIR);
DB_CONF_FILE="{0}/database.yml".format(ONAPP_CONF_DIR);
LOG_FILE="./test.log"

VERBOSE=False

PY_VER=sys.version_info

def logger(s):
    l = open(LOG_FILE, "a");
    text = '[{0}] - {1}\n'.format(str(datetime.datetime.now()),s)
    l.write(text)
    l.flush();
    l.close();

def runCmd(cmd, shell=False, shlexy=True):
    if shlexy and type(cmd) is str:
        cmd = shlex.split(cmd)
    if VERBOSE: print 'Running:', ' '.join(cmd) if type(cmd) is list else cmd
    stdout, stderr = subprocess.Popen(cmd, shell=shell, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate();
    if stderr: logger("Command {0} failed, stderr: {1}".format(cmd, stderr.strip()))
    return stdout.strip();

try:
    import MySQLdb as SQL
except ImportError:
    print "MySQL not detected, attempting to install automatically..."
    runCmd(['yum','-q','-y','install','MySQL-python'])
    try:
        import MySQLdb as SQL
        print "Imported MySQL properly."
    except:
        print "Couldn't install/import MySQL. Please run `yum -y install MySQL-python`."
        raise

##Get Onapp Version as well for certain things
ONAPP_VER = runCmd('rpm -qa onapp-cp').lstrip('onapp-cp-').rstrip('.noarch').split('-')[0];
ONAPP_VER_SPLIT = ONAPP_VER.split('.');
ONAPP_VER_MAJOR = int(ONAPP_VER_SPLIT[0]);
ONAPP_VER_MINOR = int(ONAPP_VER_SPLIT[1]);
ONAPP_VER_REVIS = int(ONAPP_VER_SPLIT[2]);

arp = argparse.ArgumentParser(prog='healthcheck', description='Health check for OnApp')
# arp.add_argument('-a', '--api', help='Enable API', action='store_true')
arp.add_argument('-v', '--verbose', help='Output more info while running', action='store_true', default=False)
arp.add_argument('-q', '--quiet', help='Don\'t output normal test output.', action='store_true', default=True)
arp.add_argument('-t', '--transactions', help='View N previous days of transactions, default: 7', type=int, metavar='N', default=7)
arp.add_argument('-c', '--commands', help='Display commands for fixes, such as zombie disks or templates [BETA]', action='store_true')
arp.add_argument('-a', '--api', help='Hostname for API submission, default architecture.onapp.com', type=str, metavar='H', default='https://architecture.onapp.com')
arp.add_argument('-k', '--token', help='Token for sending data via API to architecture.onapp.com', type=str, metavar='K')
args = arp.parse_args();
VERBOSE=args.verbose;
#USER_ID=1;  # not even using local API any longer.
DISPLAY_COMMANDS=args.commands;
quiet=args.quiet;
API_TARGET=args.api;
TRANSACTION_DURATION=args.transactions;
API_TOKEN=args.token;

class colors:
    '''Colors class:
    reset all colors with colors.reset
    two subclasses fg for foreground and bg for background.
    use as colors.subclass.colorname.
    i.e. colors.fg.red or colors.bg.green
    also, the generic bold, disable, underline, reverse, strikethrough,
    and invisible work with the main class
    i.e. colors.bold
    '''
    none=reset='\033[0m'
    b=bold='\033[01m'
    disable='\033[02m'
    u=underline='\033[04m'
    reverse='\033[07m'
    strikethrough='\033[09m'
    invisible='\033[08m'
    class fg:
        black='\033[30m'
        red='\033[31m'
        green='\033[32m'
        orange='\033[33m'
        blue='\033[34m'
        purple='\033[35m'
        cyan='\033[36m'
        lightgrey='\033[37m'
        darkgrey='\033[90m'
        lightred='\033[91m'
        lightgreen='\033[92m'
        yellow='\033[93m'
        lightblue='\033[94m'
        pink='\033[95m'
        lightcyan='\033[96m'
    class bg:
        black='\033[40m'
        red='\033[41m'
        green='\033[42m'
        orange='\033[43m'
        blue='\033[44m'
        purple='\033[45m'
        cyan='\033[46m'
        lightgrey='\033[47m'

class OnappException(Exception):
    def __init__(self, d, f, reason=False):
        self.data = d;
        self.func = f;
        self.reason = reason;
        print('OnappError, Action: {0}, Data: {1}'.format(f, d))
        if self.reason: print('Reason: {0}'.format(self.reason))

PASS="{0}[+]{1}".format(colors.fg.green, colors.reset)
FAIL="{0}[-]{1}".format(colors.fg.red, colors.reset)
CHCK="{0}[?]{1}".format(colors.fg.orange, colors.reset)

def pullOAConfig(f):
    confDict = {}
    conf = open(f).read().split('\n');
    for line in conf:
        if ':' not in line: continue;
        tmp = line.strip().split(':');
        if tmp[1].strip() == '' : continue;
        confDict[tmp[0].strip()] = tmp[1].strip().strip('"').strip("'");
    logger("Gathered OnApp configuration.");
    return confDict;


def pullDBConfig(f):
    confDict = {};
    conf = open(f).read().split('\n');
    curLabel = False;
    for line in conf:
        if ':' not in line: continue;
        if line.startswith('  '):
            tmp = line.strip().split(':');
            confDict[curLabel][tmp[0].strip()] = tmp[1].strip();
        else:
            tmp = line.strip().split(':');
            if tmp[1] == '':
                curLabel = tmp[0].strip()
                confDict[curLabel] = {};
            else: confDict[tmp[0].strip()] = tmp[1].strip();
    logger("Gathered database configuration.");
    return confDict;

DB_CONFIG = pullDBConfig(DB_CONF_FILE);
ONAPP_CONFIG= pullOAConfig(ONAPP_CONF_FILE);

def dbConn(conf=None):
    if conf is None:
        conf = DB_CONFIG[DB_CONFIG['onapp_daemon']];
    return SQL.connect(host=conf['host'], user=conf['username'], passwd=conf['password'], db=conf['database'])

def dRunQuery(q, unlist=True):
    if VERBOSE: logger("Running query:{0}".format(' '.join(q.split())))
    db = dbConn();
    cur = db.cursor();
    cur.execute(q)
    res = []
    for row in cur.fetchall(): res.append(row)
    num_fields = len(cur.description)
    cur.close();
    db.close();
    if len(res) == 1 and unlist:
        if len(res[0]) == 1: return res[0][0];
        else: return res[0]
    if len(res) == 0:
        return False
    if num_fields == 1:
        ret = []
        for t in res: ret.append(t[0])
        return ret;
    return res;

dsql = dRunQuery;

#This is the shitty pretty version. Just leaving it in just to shame myself mainly.
def dRunPrettyQueryLegacy(fields, table, conditions=None):
    if type(fields) == str: fields = [fields];
    query = 'SELECT {0} FROM {1}'.format(','.join(fields), table);
    if not not conditions:
        query += ' WHERE {0}'.format(conditions)
    db = dbConn();
    cur = db.cursor();
    cur.execute(query)
    res = cur.fetchall();
    num_fields = len(cur.description)
    field_names = []
    for i in cur.description: field_names.append(i[0])
    # field_names = [i[0] for i in cur.description]
    cur.close();
    db.close();
    if num_fields == 1 and len(res) == 1:
        return res[0][0]
    output = [];
    for n, r in enumerate(res):
        o = {}
        for nn, fld in enumerate(field_names):
            if type(res[n][nn]) is datetime.datetime:
                o[fld] = str(res[n][nn])
            else:
                o[fld] = res[n][nn];
        output.append(o)
    if len(output) == 1: return output[0]
    if len(output) == 0: return False;
    return output;

def dRunPrettyQuery(q, unlist=True):
    if VERBOSE: logger("Running pretty query:{0}".format(' '.join(q.split())))
    db = dbConn();
    cur = db.cursor();
    cur.execute(q)
    res = cur.fetchall();
    num_fields = len(cur.description)
    field_names = []
    for i in cur.description: field_names.append(i[0])
    # field_names = [i[0] for i in cur.description]
    cur.close();
    db.close();
    if num_fields == 1 and len(res) == 1 and unlist:
        return res[0][0]
    if num_fields == 1 and len(res) == 1 and not unlist:
        return {field_names[0] : res[0][0]}
    output = [];
    for n, r in enumerate(res):
        o = {}
        for nn, fld in enumerate(field_names):
            if type(res[n][nn]) is datetime.datetime:
                o[fld] = str(res[n][nn])
            else:
                o[fld] = res[n][nn];
        output.append(o)
    if len(output) == 1 and unlist: return output[0]
    if len(output) == 0: return False;
    return output;

dpsql = dRunPrettyQuery;

API_AUTH = None

def apiCallForBadPython(r, data=None, method='GET', target=API_TARGET, auth=API_AUTH):
    headers = { \
        'Content-type': 'application/json', \
        'Accept': 'application/json', \
        'Authorization': 'Basic {0}'.format(auth)}
    if target.startswith('https://'):
        conn = httplib.HTTPSConnection(API_TARGET.lstrip('https://'))
    elif target.startswith('http://'):
        conn = httplib.HTTPConnection(API_TARGET.lstrip('http://'))
    else:
        raise ValueError('API Target must provide http:// or https://')
    conn.request(method, r, json.dumps(data), headers)
    response = conn.getresponse()
    status = response.status
    logger('API Call executed - {0}{1}, Status code: {2}'.format(target, r, status));
    if VERBOSE: print('API Call executed - {0}{1}, Status code: {2}'.format(target, r, status))
    if   status == 200:
        return ast.literal_eval(response.read().replace('null', 'None').replace('true', 'True').replace('false', 'False')) or True;
    elif status == 204:
        return ast.literal_eval(response.read().replace('null', 'None').replace('true', 'True').replace('false', 'False')) or True;
    elif status == 201:
        return ast.literal_eval(response.read().replace('null', 'None').replace('true', 'True').replace('false', 'False')) or True;
    return True;

def apiCall(r, data=None, method='GET', target=API_TARGET, auth=API_AUTH):
    req = Request("{0}{1}".format(target, r), json.dumps(data))
    req.add_header("Authorization", "Basic {0}".format(auth))
    req.add_header("Accept", "application/json")
    req.add_header("Content-type", "application/json")
    if method: req.get_method = lambda: method;
    caller = inspect.stack()[1][3];
    try:
        if target.startswith('https://'):
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
            ssl_context.load_default_certs();
            response = urlopen(req, context=ssl_context)
        else:
            response = urlopen(req)
    except HTTPError as err:
        print caller,"called erroneous API request: {0}{1}, error: {2}".format(target, r, str(err))
        return False;
    status = response.getcode()
    logger('API Call executed - {0}{1}, Status code: {2}'.format(target, r, status));
    if VERBOSE: print('API Call executed - {0}{1}, Status code: {2}'.format(target, r, status))
    if   status == 200:
        return ast.literal_eval(response.read().replace('null', 'None').replace('true', 'True').replace('false', 'False')) or True;
    elif status == 204:
        return ast.literal_eval(response.read().replace('null', 'None').replace('true', 'True').replace('false', 'False')) or True;
    elif status == 201:
        return ast.literal_eval(response.read().replace('null', 'None').replace('true', 'True').replace('false', 'False')) or True;

def storageAPICall(target, r, data=None, method=None):
    req = Request("http://{0}:8080{1}".format(target, r), data)
    if method: req.get_method = lambda: method;
    response = urlopen(req)
    status = response.getcode()
    #caller = inspect.stack()[1][3];
    #print 'API Call executed - {}{}, Status code: {}'.format(API_TARGET, r, status);
    return ast.literal_eval(response.read().replace('null', 'None').replace('true', 'True').replace('false', 'False'));

stapi = storageAPICall;

HOSTS={'IS':{}, 'ALL':{}, 'ZONES':{}}

if ONAPP_VER_MAJOR >= 6 and ONAPP_VER_MINOR >= 1:
    HOSTS['IS']['HVS'] = dpsql( \
    "SELECT hv.id, iss.host_id, hv.label, hv.ip_address, hv.hypervisor_type \
    FROM hypervisors AS hv \
    JOIN integrated_storage_settings AS iss ON hv.id=iss.parent_id \
    AND iss.parent_type='Hypervisor' \
    WHERE hv.hypervisor_type IN ('kvm','xen') \
    AND hv.ip_address IS NOT NULL \
    AND iss.host_id IS NOT NULL \
    AND hv.enabled=1 AND hv.ip_address NOT IN \
      (SELECT ip_address FROM backup_servers WHERE ip_address IS NOT NULL) \
    ORDER BY hv.id", unlist=False )

    HOSTS['IS']['BSS'] = dpsql( \
    "SELECT hv.id, iss.host_id, hv.label, hv.ip_address, 'backup' as hypervisor_type \
    FROM hypervisors AS hv \
    JOIN integrated_storage_settings AS iss ON hv.id=iss.parent_id \
    AND iss.parent_type='BackupSrver' \
    WHERE ip_address IS NOT NULL \
    AND host_id IS NOT NULL \
    AND enabled=1 AND ip_address IN \
      (SELECT ip_address FROM backup_servers WHERE ip_address IS NOT NULL) \
    ORDER BY id", unlist=False )
else:
    HOSTS['IS']['HVS'] = dpsql( \
    "SELECT id, host_id, label, ip_address, hypervisor_type \
    FROM hypervisors \
    WHERE hypervisor_type IN ('kvm','xen') \
    AND ip_address IS NOT NULL \
    AND host_id IS NOT NULL \
    AND enabled=1 AND ip_address NOT IN \
      (SELECT ip_address FROM backup_servers WHERE ip_address IS NOT NULL) \
    ORDER BY id", unlist=False )

    HOSTS['IS']['BSS'] = dpsql( \
    "SELECT id, host_id, label, ip_address, 'backup' as hypervisor_type \
    FROM hypervisors \
    WHERE ip_address IS NOT NULL \
    AND host_id IS NOT NULL \
    AND enabled=1 AND ip_address IN \
      (SELECT ip_address FROM backup_servers WHERE ip_address IS NOT NULL) \
    ORDER BY id", unlist=False )

HOSTS['ALL']['HVS'] = dpsql( \
"SELECT id, label, ip_address, hypervisor_type \
FROM hypervisors \
WHERE hypervisor_type IN ('kvm','xen') \
AND ip_address IS NOT NULL \
AND enabled=1 AND ip_address NOT IN \
  (SELECT ip_address FROM backup_servers WHERE ip_address IS NOT NULL) \
ORDER BY id", unlist=False)

HOSTS['ALL']['BSS'] = dpsql( \
"SELECT id, label, ip_address, 'backup' AS hypervisor_type \
FROM backup_servers \
WHERE ip_address IS NOT NULL  \
AND enabled=1 ORDER BY id", unlist=False)

HV_ZONES = "SELECT DISTINCT p.id FROM packs AS p \
JOIN hypervisors AS hv ON hv.hypervisor_group_id=p.id \
WHERE p.type='HypervisorGroup' \
GROUP BY p.id \
HAVING count(hv.id) > 0;"


if ONAPP_VER_MAJOR >= 6 and ONAPP_VER_MINOR >= 1:
    for zid in dsql(HV_ZONES, unlist=False):
        HOSTS['ZONES'][zid] = dpsql("SELECT label FROM packs WHERE id={0}".format(zid), unlist=False)
        HOSTS['ZONES'][zid]['HV'] = {}
        for hvid in dsql("SELECT id FROM hypervisors WHERE hypervisor_group_id={0} AND enabled=1".format(zid), unlist=False):
            HOSTS['ZONES'][zid]['HV'][hvid] = dpsql( \
                "SELECT hv.id, iss.host_id, hv.label, hv.ip_address, hv.hypervisor_type \
                 FROM hypervisors AS hv JOIN integrated_storage_settings AS iss ON hv.id=iss.parent_id \
                 WHERE hv.id={0}".format(hvid) )
        bsids = dsql("SELECT backup_server_id FROM backup_server_joins WHERE \
            target_join_type='HypervisorGroup' AND target_join_id={0}".format(zid), unlist=False)
        HOSTS['ZONES'][zid]['BS'] = {};
        if bsids:
            for bsid in bsids:
                HOSTS['ZONES'][zid]['BS'][bsid] = dpsql("SELECT id, label, ip_address, 'backup' as hypervisor_type \
                    FROM backup_servers WHERE id={0}".format(bsid));
                HOSTS['ZONES'][zid]['BS'][bsid]['host_id'] = dsql("SELECT iss.host_id \
                    FROM hypervisors AS hv JOIN integrated_storage_settings AS iss ON hv.id=iss.parent_id \
                    WHERE hv.ip_address='{0}'" \
                         .format(HOSTS['ZONES'][zid]['BS'][bsid]['ip_address']))
else:
    for zid in dsql(HV_ZONES, unlist=False):
        HOSTS['ZONES'][zid] = dpsql("SELECT label FROM packs WHERE id={0}".format(zid), unlist=False)
        HOSTS['ZONES'][zid]['HV'] = {}
        for hvid in dsql("SELECT id FROM hypervisors WHERE hypervisor_group_id={0} AND enabled=1".format(zid), unlist=False):
            HOSTS['ZONES'][zid]['HV'][hvid] = dpsql( \
                "SELECT id, host_id, label, ip_address, hypervisor_type \
                 FROM hypervisors WHERE id={0}".format(hvid) )
        bsids = dsql("SELECT backup_server_id FROM backup_server_joins WHERE \
            target_join_type='HypervisorGroup' AND target_join_id={0}".format(zid), unlist=False)
        HOSTS['ZONES'][zid]['BS'] = {};
        if bsids:
            for bsid in bsids:
                HOSTS['ZONES'][zid]['BS'][bsid] = dpsql("SELECT id, label, ip_address, 'backup' as hypervisor_type \
                    FROM backup_servers WHERE id={0}".format(bsid));
                HOSTS['ZONES'][zid]['BS'][bsid]['host_id'] = dsql("SELECT host_id FROM hypervisors WHERE ip_address='{0}'" \
                         .format(HOSTS['ZONES'][zid]['BS'][bsid]['ip_address']))



# IS_HOST_INFO=dpsql( \
# "SELECT host_id, ip_address, label, hypervisor_type FROM \
#   (SELECT id, host_id, label, ip_address, hypervisor_type, 1 AS row_order \
#   FROM hypervisors \
#   WHERE hypervisor_type IN ('kvm','xen') \
#   AND ip_address IS NOT NULL \
#   AND host_id IS NOT NULL \
#   AND enabled=1 AND ip_address NOT IN \
#     (SELECT ip_address FROM backup_servers WHERE ip_address IS NOT NULL) \
#   UNION  \
#   SELECT id, host_id, label, ip_address, 'backup' as hypervisor_type, 2 AS row_order \
#   FROM hypervisors \
#   WHERE ip_address IS NOT NULL \
#   AND host_id IS NOT NULL \
#   AND enabled=1 AND ip_address IN \
#     (SELECT ip_address FROM backup_servers WHERE ip_address IS NOT NULL) \
#   ORDER BY row_order, id) AS T")
#
# HOST_INFO=dpsql( \
# "SELECT id, label, ip_address, hypervisor_type FROM ( \
#   SELECT id, label, ip_address, hypervisor_type, 1 AS row_order \
#   FROM hypervisors \
#   WHERE hypervisor_type IN ('kvm','xen') \
#   AND ip_address IS NOT NULL \
#   AND enabled=1 AND ip_address NOT IN \
#     (SELECT ip_address FROM backup_servers WHERE ip_address IS NOT NULL) \
#   UNION \
#   SELECT id, label, ip_address, 'backup', 2 AS row_order \
#   FROM backup_servers \
#   WHERE ip_address IS NOT NULL  \
#   AND enabled=1 \
#   ORDER BY row_order, id) AS T")




def checkHVBSStatus(target):
    rData = {};
    vm_list = [];
    hv_ver_bash_cmd = "ssh -p{0} root@{1} \"cat /onapp/onapp-store-install.version 2>/dev/null || cat /onapp/onapp-hv-tools.version 2>/dev/null || grep Version /onappstore/package-version.txt 2>/dev/null || echo '???'\""
    hv_ver_cmd = [ 'su', 'onapp', '-c', hv_ver_bash_cmd.format(ONAPP_CONFIG['ssh_port'], target['ip_address']) ]
    hv_kernel_cmd = [ 'su', 'onapp', '-c', 'ssh -p{0} root@{1} "uname -r 2>/dev/null" 2>/dev/null'.format(ONAPP_CONFIG['ssh_port'], target['ip_address']) ]
    hv_distro_cmd = [ 'su', 'onapp', '-c', 'ssh -p{0} root@{1} "cat /etc/redhat-release 2>/dev/null" 2>/dev/null'.format(ONAPP_CONFIG['ssh_port'], target['ip_address']) ]
    rData['version'] = runCmd(hv_ver_cmd);
    rData['kernel'] = runCmd(hv_kernel_cmd);
    rData['distro'] = runCmd(hv_distro_cmd);
    rData['loadavg'] = runCmd(['su','onapp','-c','ssh -p{0} root@{1} "cat /proc/loadavg"'.format(ONAPP_CONFIG['ssh_port'], target['ip_address'])])
    rData['memory'] = runCmd(['su','onapp','-c','ssh -p{0} root@{1} "free -m"'.format(ONAPP_CONFIG['ssh_port'], target['ip_address'])]).split('\n')[1].split()[1]
    rData['freemem'] = runCmd(['su','onapp','-c','ssh -p{0} root@{1} "free -m"'.format(ONAPP_CONFIG['ssh_port'], target['ip_address'])]).split('\n')[1].split()[2]
    hv_vms = dsql("SELECT identifier FROM virtual_machines WHERE hypervisor_id = {0} AND booted=1 AND identifier IS NOT NULL".format(target['id']), False)
    if hv_vms is False:
        hv_vms = [];
    running_vms = []
    if target['hypervisor_type'] == 'kvm':
        vm_from_hv = runCmd(['su','onapp','-c','ssh -p{0} root@{1} "virsh list --state-running"'.format(ONAPP_CONFIG['ssh_port'], target['ip_address'])])
        vm_list = vm_from_hv.split('\n')
        del vm_list[0]
        del vm_list[0]
        # print vm_list
        for t in vm_list:
            # print "t = ", t
            if "STORAGENODE" not in t:
                running_vms.append(t.split()[1])
        # vm_list = [ t.split()[1] for t in vm_list if "STORAGENODE" not in t.split()[1] ]
    if target['hypervisor_type'] == 'xen':
        vm_from_hv = runCmd(['su','onapp','-c','ssh -p{0} root@{1} "xm list --state=running"'.format(ONAPP_CONFIG['ssh_port'], target['ip_address'])])
        vm_list = vm_from_hv.split('\n')
        del vm_list[0]
        for t in vm_list:
            # print "t = ", t
            if "Domain-0" not in t and "STORAGENODE" not in t:
                running_vms.append(t.split()[0])
        # vm_list = [ x for x in vm_list if 'Domain-0' not in x ]
        # vm_list = [ t.split()[0] for t in vm_list if "STORAGENODE" not in t.split()[1] ]
    cloned_hvvms = copy(hv_vms)
    zombie_vms = [];
    for vm in running_vms:
        try:
            cloned_hvvms.remove(vm)
        except ValueError:
            print('!!! Virtual Machine {0} is booted on the hypervisor but not booted in database !!!'.format(vm))
            logger('! Virtual Machine {0} is bootedon the hypervisor but not booted in database'.format(vm))
            zombie_vms.append(vm)
    if len(cloned_hvvms) > 0:
        print '!!! Virtual machines found running in database, but not on the hypervisor: ', ','.join(cloned_hvvms)
        logger('! Virtual machines found running in database, but not on the hypervisor: {0}'.format(','.join(cloned_hvvms)))
    if len(zombie_vms): rData['zombie_vms'] = zombie_vms;
    if len(cloned_hvvms): rData['dead_vms'] = cloned_hvvms;
    #### Create also for xen hypervisors...
    return rData;

def checkHVConn(from_ip, to_ip):
    cmd = "ssh -p{0} root@{1} 'ping -w1 {2}'".format(ONAPP_CONFIG['ssh_port'], from_ip, to_ip)
    rData = runCmd(['su', 'onapp', '-c', cmd])
    return 0 if rData == '' else 1

def checkNetJoins(zone_id):
    network_ids = dsql("SELECT network_id FROM networking_network_joins WHERE target_join_id={0}".format(zone_id), unlist=False)
    if network_ids is False: return False
    labels = [];
    for nid in network_ids:
        network_label = dsql("SELECT label FROM networking_networks WHERE id={0}".format(nid))
        labels.append(network_label)
    return labels;

def checkDataJoins(zone_id):
    datazone_ids = dsql("SELECT data_store_id FROM data_store_joins WHERE target_join_id={0}".format(zone_id), unlist=False)
    if datazone_ids is False: return False
    labels = [];
    for dzid in datazone_ids:
        datazone_label = dsql("SELECT label FROM data_stores WHERE id={0}".format(dzid))
        labels.append(datazone_label)
    return labels;

def checkBackupJoins(zone_id):
    backup_ids = dsql("SELECT backup_server_id FROM backup_server_joins WHERE target_join_id={0}".format(zone_id), unlist=False)
    if backup_ids is False: return False
    labels = [];
    for bsid in backup_ids:
        backup_label = dsql("SELECT label FROM backup_servers WHERE id={0}".format(bsid))
        labels.append(backup_label)
    return labels;

def checkComputeZones(zone_id=False):
    zone_data = {};
    zone_ids = HOSTS['ZONES'].keys();
    if zone_id is False and type(zone_ids) is not long:
        all_zone_ids = dsql("SELECT id FROM packs WHERE type='HypervisorGroup'", unlist=False)
        for zid in all_zone_ids:
            vc_check = dsql("SELECT hypervisor_type FROM hypervisors WHERE hypervisor_group_id={0} AND hypervisor_type NOT IN ('vcenter','vcloud')".format(zid))
            if vc_check is False: continue
            zone_data[zid] = {'zone_id': zid, 'label':HOSTS['ZONES'][zid]['label'], 'network_joins':checkNetJoins(zid), \
                'data_store_joins':checkDataJoins(zid), 'backup_server_joins':checkBackupJoins(zid)}
    elif type(zone_id) is list:
        for zid in zone_id:
            vc_check = dsql("SELECT hypervisor_type FROM hypervisors WHERE hypervisor_group_id={0} AND hypervisor_type NOT IN ('vcenter','vcloud')".format(zid))
            if len(vc_check) == 0: continue
            zone_data[zid] = {'zone_id':zid, 'label':HOSTS['ZONES'][zid]['label'], 'network_joins':checkNetJoins(zid), \
                'data_store_joins':checkDataJoins(zid), 'backup_server_joins':checkBackupJoins(zid)}
    else:
        if type(zone_ids) is long: zone_id = zone_ids;
        vc_check = dsql("SELECT hypervisor_type FROM hypervisors WHERE hypervisor_group_id={0} AND hypervisor_type NOT IN ('vcenter','vcloud')".format(zone_id))
        if len(vc_check) == 0: logger('Requested hypervisor zone either does not exist or is all vcenter/vcloud')
        zone_data[zid] = {'zone_id':zone_id, 'label':HOSTS['ZONES'][zid]['label'], 'network_joins':checkNetJoins(zone_id), \
            'data_store_joins':checkDataJoins(zone_id), 'backup_server_joins':checkBackupJoins(zone_id)}
    return zone_data;

def cpuCheck(target=False):
    cpu_model_cmd="grep model\ name /proc/cpuinfo -m1 | cut -d':' -f2 | sed -r -e 's/^ //;s/ $//'"
    cpu_speed_cmd="grep cpu\ MHz /proc/cpuinfo -m1 | cut -d':' -f2 | cut -d'.' -f1 | tr -d ' '"
    cpu_cores_cmd="grep -c ^processor /proc/cpuinfo"
    if target is False:
        rData = { \
        'model':runCmd("grep model\ name /proc/cpuinfo -m1").split(':')[1].strip(), \
        'speed':runCmd("grep cpu\ MHz /proc/cpuinfo -m1").split(':')[1].strip(), \
        'cores':runCmd("grep -c ^processor /proc/cpuinfo") }
        return rData;
    rData = {};
    rData['model'] = runCmd(['su', 'onapp', '-c', 'ssh -p{0} root@{1} "{2}"'.format(ONAPP_CONFIG['ssh_port'], target, cpu_model_cmd)])
    rData['speed'] = runCmd(['su', 'onapp', '-c', 'ssh -p{0} root@{1} "{2}"'.format(ONAPP_CONFIG['ssh_port'], target, cpu_speed_cmd)])
    rData['cores'] = runCmd(['su', 'onapp', '-c', 'ssh -p{0} root@{1} "{2}"'.format(ONAPP_CONFIG['ssh_port'], target, cpu_cores_cmd)])
    return rData;

def motherboardCheck(target=False):
    base_cmd = "dmidecode -s baseboard-{0}"
    if target is False:
        return { \
        'manufacturer' : runCmd(base_cmd.format('manufacturer')) ,
        'product-name' : runCmd(base_cmd.format('product-name')) ,
        'version' : runCmd(base_cmd.format('version')) }
    rData = {};
    rData['manufacturer'] = runCmd(['su', 'onapp', '-c', 'ssh -p{0} root@{1} "{2}"'.format(ONAPP_CONFIG['ssh_port'], target, base_cmd.format('manufacturer'))])
    rData['product-name'] = runCmd(['su', 'onapp', '-c', 'ssh -p{0} root@{1} "{2}"'.format(ONAPP_CONFIG['ssh_port'], target, base_cmd.format('product-name'))])
    rData['version'] = runCmd(['su', 'onapp', '-c', 'ssh -p{0} root@{1} "{2}"'.format(ONAPP_CONFIG['ssh_port'], target, base_cmd.format('version'))])
    return rData;

def chassisCheck(target=False):
    base_cmd = "dmidecode -s chassis-{0}"
    if target is False:
        return { \
        'manufacturer' : runCmd(base_cmd.format('manufacturer')) ,
        'type' : runCmd(base_cmd.format('type')) ,
        'version' : runCmd(base_cmd.format('version')) }
    rData = {}
    rData['manufacturer'] = runCmd(['su', 'onapp', '-c', 'ssh -p{0} root@{1} "{2}"'.format(ONAPP_CONFIG['ssh_port'], target, base_cmd.format('manufacturer'))])
    rData['type'] = runCmd(['su', 'onapp', '-c', 'ssh -p{0} root@{1} "{2}"'.format(ONAPP_CONFIG['ssh_port'], target, base_cmd.format('type'))])
    rData['version'] = runCmd(['su', 'onapp', '-c', 'ssh -p{0} root@{1} "{2}"'.format(ONAPP_CONFIG['ssh_port'], target, base_cmd.format('version'))])
    return rData;

def diskHWCheck(target=False):
    #list_disks_cmd = "lsblk -n -d -e 1,7,11 -oNAME"
    list_disks_cmd = "lsblk -dn -oNAME -I8,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99,100,101,102,103,104,105,106,107,108,109,110,111,112,113,114,115,116,117,118,119,120,121,122,123,124,125,126,127,128,129,130,131,132,133,134,135"
    udev_cmd = "bash -c 'eval $(udevadm info --export --query=property --path=/sys/class/block/{0}) && echo $ID_VENDOR - $ID_MODEL'"
    disk_data = {}
    if target is False:
        disks = runCmd(list_disks_cmd, shlexy=False, shell=True).split('\n')
        for d in disks:
            disk_data[d] = runCmd(udev_cmd.format(d), shlexy=False, shell=True)
        return disk_data;
    disks = runCmd(['su', 'onapp', '-c', 'ssh -p{0} root@{1} "{2}"'.format(ONAPP_CONFIG['ssh_port'], target, list_disks_cmd)]).split('\n')
    udev_cmd = "bash -c 'eval \$(udevadm info --export --query=property --path=/sys/class/block/{0}) && echo \$ID_VENDOR - \$ID_MODEL'"
    for d in disks:
        disk_data[d] = runCmd(['su', 'onapp', '-c', 'ssh -p{0} root@{1} "{2}"'.format(ONAPP_CONFIG['ssh_port'], target, udev_cmd.format(d))])
    return disk_data;

def interfaceCheck(target=False):
    iface_cmd = "find /sys/class/net -type l -not -lname '*virtual*' -printf '/sys/class/net/%f\n'"
    udev_cmd = "udevadm info --export --query=property --path=`readlink -f {0}` | grep ID_MODEL_FROM_DATABASE"
    iface_data = {}
    if target is False:
        iface_list = runCmd(iface_cmd).split('\n')
        for iface in iface_list:
            tmpface = runCmd(udev_cmd.format(iface), shell=True, shlexy=False)
            if tmpface == '':
                iface_data[iface.split('/')[1]] = 'N/A'
            else:
                iface_data[iface.split('/')[-1]] = tmpface.split('=')[1].strip("'")
        return iface_data;
    iface_list = runCmd(['su', 'onapp', '-c', 'ssh -p{0} root@{1} "{2}"'.format(ONAPP_CONFIG['ssh_port'], target, iface_cmd)]).split('\n')
    udev_cmd = "bash -c 'udevadm info --export --query=property --path=`readlink -f {0}` | grep ID_MODEL_FROM_DATABASE'"
    for iface in iface_list:
        tmpface = runCmd(['su', 'onapp', '-c', 'ssh -p{0} root@{1} "{2}"'.format(ONAPP_CONFIG['ssh_port'], target, udev_cmd.format(iface))])
        if tmpface == '':
            iface_data[iface.split('/')[-1]] = 'N/A'
        else:
            iface_data[iface.split('/')[-1]] = tmpface.split('=')[1].strip("'")
    return iface_data;

#def checkISHealth(ds_data):

def checkDataStore(target_id):
    logger("Checking data store id = {0}".format(target_id))
    if VERBOSE: print "Checking data store id {0}".format(target_id)
    ds_data = dpsql("SELECT id, label, identifier, local_hypervisor_id, data_store_size, hypervisor_group_id, \
        integrated_storage_cache_enabled as is_cache_enabled, integrated_storage_cache_settings as is_cache_settings, \
        io_limits, data_store_type FROM data_stores WHERE id={0}".format(target_id))
    disk_count = dpsql("SELECT count(*) FROM disks WHERE built=1 AND data_store_id={0}".format(target_id))
    db_disk_ids = dsql("SELECT identifier FROM disks WHERE data_store_id={0} AND built=1".format(target_id))
    ds_data['disk_count'] = disk_count;
    hv_zone_id = dsql("SELECT target_join_id FROM data_store_joins WHERE data_store_id={0} AND target_join_type='HypervisorGroup'".format(target_id))
    # The HV_ID should never return a list because data stores should only be able to be joined to one zone at a time.
    # zombie disks
    if ds_data['data_store_type'] == 'lvm':
        if ds_data['local_hypervisor_id'] is not None:
            target_ip = dsql("SELECT ip_address FROM hypervisors WHERE id={0}".format(ds_data['local_hypervisor_id']))
            if VERBOSE: print("Using local hypervisor at {0}".format(target_ip))
            logger("Using local hypervisor at {0}".format(target_ip))
        else:
            target_ip = dsql("SELECT ip_address FROM hypervisors WHERE hypervisor_group_id={0} LIMIT 1".format(hv_zone_id))
            if VERBOSE: print("Using first hypervisor at {0} from group id {1}".format(target_ip, hv_zone_id))
            logger("Using first hypervisor at {0} from group id {1}".format(target_ip, hv_zone_id))
        lvs_output = runCmd(['su', 'onapp', '-c', 'ssh -p{0} root@{1} "lvs {2} --noheadings"'.format(ONAPP_CONFIG['ssh_port'], target_ip, ds_data['identifier'])]).split('\n')
        lv_disks = []
        for line in lvs_output:
            lv_disks.append(line.split()[0])
        # lv_disks = [line.split()[0] for line in lvs_output];
        logger("Adding all LVM disk sizes together. ")
        if VERBOSE: print "Adding all LVM disk sizes together"
        lv_sizes = []
        for n in runCmd(['su', 'onapp', '-c', "ssh -p{0} root@{1} lvs {2} -o LV_SIZE --noheadings --units g --nosuffix"]).format(ONAPP_CONFIG['ssh_port'], target_ip, ds_data['identifier']).split():
            lv_sizes.append(float(n))
        # lv_sizes = [ float(n) for n in runCmd("lvs -o LV_SIZE --noheadings --units g --nosuffix").split() ]
        lv_size_sum = sum(lv_sizes)
        if VERBOSE: print "Total size: {0}g".format(lv_size_sum)
        logger("Total size: {0}g".format(lv_size_sum))
        ds_data['missing_disks'] = [];
        if not not db_disk_ids:
            for disk in db_disk_ids:
                try:
                    lv_disks.remove(disk)
                except ValueError:
                    print('!!! Disk {0} found in database is NOT in LVM data store {1} !!!'.format(disk, ds_data['identifier']))
                    logger('! Missing disk {0} is in database but not in LVM data store {1}'.format(disk, ds_data['identifier']))
                    ds_data['missing_disks'].append(disk)
        if len(lv_disks) > 0:
            print ' !!! Zombie disks found:', ','.join(lv_disks)
            logger('! Zombie disks found: '+','.join(lv_disks))
            if DISPLAY_COMMANDS:
                print 'Displaying removal commands for zombie disks: '
                for disk in lv_disks:
                    print 'rm -f /dev/{0}/{1}'.format(ds_data['identifier'], disk)
        ds_data['zombie_disks'] = lv_disks;
        ds_data['hv_disk_size_total'] = lv_size_sum;
    if ds_data['data_store_type'] == 'is':
        target_ip = dsql("SELECT ip_address FROM hypervisors WHERE hypervisor_group_id={0} \
            AND host_id IS NOT NULL LIMIT 1".format(ds_data['hypervisor_group_id']))
        is_ds = stapi(target=target_ip,r='/is/Datastore/{0}'.format(ds_data['identifier']))[ds_data['identifier']]
        is_disks = is_ds['vdisks'].split(',')
        node_sizes = {}
        for node in is_ds['members'].split(','):
            tmp = stapi(target_ip, '/is/Node/{0}'.format(node))[node]['utilization']
            node_sizes = { node : tmp }
        ds_data['average_node_usage'] = (sum(node_sizes.values())/len(node_sizes))
        ds_data['missing_disks'] = [];
        if not not db_disk_ids:
            for disk in db_disk_ids:
                try:
                    is_disks.remove(disk)
                except ValueError:
                    print('{0}!!! Disk {1} found in database is NOT in IS data store {2} !!!{3}'.format( \
                        colors.fg.red, disk, ds_data['identifier'], colors.none))
                    logger('! Missing disk {0} is in database but not in IS data store {1}'.format(disk, ds_data['identifier']))
                    ds_data['missing_disks'].append(disk)
        if len(is_disks) > 0:
            print ' !!! Zombie disks found:', ','.join(is_disks)
            logger('! Zombie disks found: '+','.join(is_disks))
            if DISPLAY_COMMANDS:
                print 'Displaying removal commands for zombie disks(check that these disks are not mounted first): '
                for disk in is_disks:
                    print 'onappstore offline uuid={0}'.format(disk)
                for disk in is_disks:
                    print 'onappstore remove uuid={0}'.format(disk)
        ds_data['zombie_disks'] = is_disks;
        ds_data['data_store_size'] = ((is_ds['total_usable_size']/1024.0)/1024.0)/1024.0
        #ds_data['is_health'] = checkISHealth(ds_data)
    ds_data['db_disk_size_total'] = int(dsql("SELECT SUM(disk_size) FROM disks WHERE data_store_id={0} AND built=1".format(ds_data['id'])) or 0)
    return ds_data;

def checkBackups(target):
    if type(target) is dict and 'id' in target.keys():
        target = target['id']
    else:
        raise ValueError('Backup Server ID not found when calling checkBackups')
    if VERBOSE: print "Checking backups on server id {0}".format(target)
    data = {'missing':[], 'zombie':[]};
    # go through one backup server and check the backups with those in the database.
    bs_data = dpsql("SELECT id, ip_address, capacity FROM backup_servers WHERE id={0}".format(target))
    backups_in_db = dsql("SELECT identifier FROM backups WHERE backup_server_id={0}".format(target), unlist=False)
    backups_on_server_fullpath = runCmd(['su', 'onapp', '-c', 'ssh -p{0} root@{1} "ls -d -1 {2}/[a-z]/[a-z0-9]/* 2>/dev/null || echo FAIL"'.format(ONAPP_CONFIG['ssh_port'], bs_data['ip_address'], ONAPP_CONFIG['backups_path'])]).split('\n')
    if backups_on_server_fullpath == ['FAIL'] or backups_on_server_fullpath == '' or backups_on_server_fullpath == 'FAIL':
        return False
    backups_on_server = []
    for line in backups_on_server_fullpath:
        backups_on_server.append(line.replace(ONAPP_CONFIG['backups_path'], '').lstrip('/').split('/')[2])
    # backups_on_server = [line.replace(ONAPP_CONFIG['backups_path'], '').lstrip('/').split('/')[2] for line in backups_on_server_fullpath]
    for backup in backups_in_db:
        try:
            backups_on_server.remove(backup);
        except ValueError:
            print('{0}!!! Backup found in database but not on disk at {1}/{2}/{3}/{4} on backup server {5}{6}'.format( \
                colors.fg.red, ONAPP_CONFIG['backups_path'], backup[0], backup[1], backup, bs_data['ip_address'], colors.none))
            logger('!!! Backup found in database but not on disk at {0}/{1}/{2}/{3} on backup server {4}'.format( \
                ONAPP_CONFIG['backups_path'], backup[0], backup[1], backup, bs_data['ip_address']))
            data['missing'].append(backup)
    if len(backups_on_server) > 0:
        print(colors.fg.yellow, '!!! Zombie backups found: ', ','.join(backups_on_server), colors.none)
        logger('!!! Zombie backups found: {0}'.format(','.join(backups_on_server)))
        if DISPLAY_COMMANDS:
            print 'Displaying removal commands for zombie backups: '
            for backups in backups_on_server:
                print 'rm -rf {0}/{1}/{2}/{3}'.format(ONAPP_CONFIG['backups_path'], backup[0], backup[1], backup)
    data['zombie'] = backups_on_server;
    return data;
    # maybe have it come check disk space vs the database sizes to find "empty" backups?
    # backup_sizes_in_db = { t[0] : t[1] for t in dsql("SELECT identifier, backup_size FROM backups WHERE backup_server_id={}".format(target)) }
    # inc_backups_by_vm = {}
    # inc_backups_in_db = dsql('SELECT identifier, target_id FROM backups WHERE \
    #         type="BackupIncremental" AND target_type="VirtualMachine" AND backup_server_id={} \
    #         ORDER BY created_at'.format(target))
    # for vm in inc_backups_in_db:
    #     if vm[1] not in inc_backups_by_vm.keys():
    #         inc_backups_by_vm[vm[1]] = [vm[0]]
    #     else:
    #         inc_backups_by_vm[vm[1]].append(vm[0])
    # for vm in inc_backups_by_vm.keys():
    #     tmp = [ '{}/{}/{}/{}'.format(ONAPP_CONFIG['backups_path'], b[0], b[1], b) for b in inc_backups_by_vm[vm]]
    #     server_blist = runCmd(['su', 'onapp', '-c', 'ssh -p{} root@{} "du -sk {}"'.format(ONAPP_CONFIG['ssh_port'], bs_data['ip_address'], ' '.join(tmp))]).split('\n')
    #     backup_sizes_on_server = { t.split('\t')[1].split('/')[-1] : int(t.split('\t')[0]) for t in server_blist }
    # norm_backups_in_db = dsql('SELECT identifier, target_id FROM backups WHERE \
    #         backup_server_id={} AND type="BackupNormal"'.format(target))
    # tmp = [ '{}/{}/{}/{}'.format(ONAPP_CONFIG['backups_path'], b[0], b[1], b) for b in norm_backups_in_db ]
    # for path in tmp:
    #     server_du = runCmd(['su', 'onapp', '-c', 'ssh -p{} root@{} "du -sk {}"'.format(ONAPP_CONFIG['ssh_port'], bs_data['ip_address'], path)]).split('\t')
    #     backup_sizes_on_server[server_du[1]] = server_du[0]
    # #for backups in backup_sizes_in_db.keys():
    #     #go through each one, compare it to the values I got previously, report differences.

def mainFunction():
    health_data = {}
    health_data['cp_data'] = { \
        'version' : runCmd("rpm -qa onapp-cp") , \
        'kernel': runCmd("uname -r") , \
        'distro' : runCmd("cat /etc/redhat-release") , \
        'memory' : runCmd("free -m").split('\n')[1].split()[1] , \
        'freemem' : runCmd("free -m").split('\n')[1].split()[2] , \
        'loadavg' : runCmd("cat /proc/loadavg"), \
        'timezone' : runCmd("readlink /etc/localtime").lstrip('../usr/share/zoneinfo/') , \
        'ip_address' : runCmd("ip route get 1 | awk '{print $NF;exit}'", shell=True, shlexy=False) , \
        'motherboard' : motherboardCheck(), \
        'chassis' : chassisCheck(), \
        'disks' : diskHWCheck(), \
        'network_interfaces' : interfaceCheck(), \
        'cpu' : cpuCheck()}
    health_data['cp_data']['vm_data'] = { \
        'off' : dsql('SELECT count(*) AS count FROM virtual_machines WHERE booted=0 AND deleted_at IS NULL') ,\
        'on' : dsql('SELECT count(*) AS count FROM virtual_machines WHERE booted=1 AND deleted_at IS NULL') ,\
        'failed' : dsql('SELECT count(*) AS count FROM virtual_machines WHERE state="failed" AND deleted_at IS NULL') }
    health_data['cp_data']['zones'] = checkComputeZones();
    if not quiet:
        fs = '{0:>20s} : {2}'
        print fs.format('Version', health_data['cp_data']['version'])
        print fs.format('Kernel', health_data['cp_data']['kernel'])
        print fs.format('Distribution', health_data['cp_data']['distro'])
        print fs.format('RAM', health_data['cp_data']['memory'])
        print fs.format('Free RAM', health_data['cp_data']['freemem'])
        print fs.format('Load Average', health_data['cp_data']['loadavg'])
        print fs.format('Timezone', health_data['cp_data']['timezone'])
        print fs.format('CPU Model', health_data['cp_data']['cpu']['model'])
        print '{0:>20s} : {2} MHz'.format('CPU Speed', health_data['cp_data']['cpu']['speed'])
        print fs.format('CPU Cores', health_data['cp_data']['cpu']['cores'])
        print fs.format('Total VMs ON / OFF', '{0} / {2}'.format( \
            health_data['cp_data']['vm_data']['off'], health_data['cp_data']['vm_data']['on']))
        if health_data['cp_data']['vm_data']['failed'] is not False:
            print fs.format('Total VMs FAIL', health_data['cp_data']['vm_data']['failed'])
        print '{0:-^45}'.format('')
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    for zone in health_data['cp_data']['zones'].keys():
        health_data['cp_data']['zones'][zone]['hypervisors'] = {}
        for hv in HOSTS['ZONES'][zone]['HV'].itervalues():
            ## it seems like the first SNMP connection would register 0, then give a good value afterwards
            ## so... gonna prime it just in case:
            primer = sock.connect_ex((hv['ip_address'], 161))
            del primer;
            tmp = {};
            tmp['connectivity'] = {'storage_network':{}, 'all':{}}
            ping_cmd = [ 'ping', hv['ip_address'], '-w1' ]
            ssh_cmd = [ 'su',  'onapp',  '-c', "ssh -o ConnectTimeout=10 -p{0} root@{1} \'echo connected\'".format(ONAPP_CONFIG['ssh_port'], hv['ip_address']) ]
            tmp['connectivity']['ping'] = 0 if runCmd(ping_cmd) == '' else 1;
            tmp['connectivity']['ssh'] = 0 if runCmd(ssh_cmd) == '' else 1;
            tmp['connectivity']['snmp'] = 0 if sock.connect_ex((hv['ip_address'], 161)) == 0 else 1;
            if tmp['connectivity']['ssh'] == 0:
                health_data['cp_data']['zones'][zone]['hypervisors'][hv['id']] = tmp
                continue;
            tmp_status = checkHVBSStatus(hv)
            tmp.update(tmp_status)
            tmp['id'] = hv['id']
            tmp['type'] = hv['hypervisor_type']
            tmp['ip_address'] = hv['ip_address']
            tmp['label'] = hv['label']
            tmp['cpu'] = cpuCheck(hv['ip_address'])
            tmp['motherboard'] = motherboardCheck(hv['ip_address'])
            tmp['chassis'] = chassisCheck(hv['ip_address'])
            tmp['disks'] = diskHWCheck(hv['ip_address'])
            tmp['network_interfaces'] = interfaceCheck(hv['ip_address'])
            tmp['vm_data'] = { \
                'off' : dsql('SELECT count(*) AS count FROM virtual_machines \
                              WHERE booted=0 AND hypervisor_id={0} AND deleted_at IS NULL'.format(hv['id'])) ,\
                'on' : dsql('SELECT count(*) AS count FROM virtual_machines \
                             WHERE booted=1 AND hypervisor_id={0} AND deleted_at IS NULL'.format(hv['id'])) ,\
                'failed' : dsql('SELECT count(*) AS count FROM virtual_machines \
                                 WHERE state="failed" AND hypervisor_id={0} AND deleted_at IS NULL'.format(hv['id'])) }
            if not quiet:
                #print all the hypervisor data
                fs = '{0:>20s} : {1}'
                if hv['hypervisor_type'] == 'backup': print 'Backup Server ID {0}'.format(tmp['id'])
                else: print 'Hypervisor ID {0}'.format(tmp['id'])
                print fs.format('Label', tmp['label'])
                print fs.format('IP Address', tmp['ip_address'])
                print fs.format('Seen via', 'Ping:{0}, SSH:{1}, SNMP:{2}'.format( \
                    PASS if tmp['ping'] else FAIL, \
                    PASS if tmp['ssh'] else FAIL, \
                    PASS if tmp['snmp'] else FAIL))
                print fs.format('CPU Model', tmp['cpu']['model'])
                print fs.format('Cores', '{0} @ {1} MHz'.format(tmp['cpu']['cores'], tmp['cpu']['speed']))
                print fs.format('Kernel', tmp['kernel'])
                print fs.format('Distro', tmp['distro'])
                print fs.format('OnApp Version', tmp['version'])
                print fs.format('Memory', '{0} free / {1} MB'.format(tmp['freemem'], tmp['memory']))
                print fs.format('Loadavg', tmp['loadavg'])
                print fs.format('Total VMs ON / OFF', '{0} / {1}'.format(tmp['vm_data']['on'], tmp['vm_data']['off']))
                if tmp['vm_data']['failed'] > 0:
                    print fs.format('Total VMs FAILED', tmp['vm_data']['failed'])
                if 'zombie_vms' in tmp.keys():
                    print fs.format('Zombie VMs', ','.join(tmp['zombie_vms']))
                print '{:-^45}'.format('')
            for t in HOSTS['ZONES'][zone]['HV'].itervalues():
                tmp['connectivity']['all'][t['id']] = checkHVConn(hv['ip_address'], t['ip_address'])
            for t in HOSTS['ZONES'][zone]['BS'].itervalues():
                tmp['connectivity']['all']['B{0}'.format(t['id'])] = checkHVConn(hv['ip_address'], t['ip_address'])
            if hv['host_id']:
                for t in HOSTS['ZONES'][zone]['HV'].itervalues():
                    tmp['connectivity']['storage_network'][t['id']] = checkHVConn(hv['ip_address'], '10.200.{0}.254'.format(t['host_id']))
                for t in HOSTS['ZONES'][zone]['BS'].itervalues():
                    tmp['connectivity']['storage_network']['B{0}'.format(t['id'])] = checkHVConn(hv['ip_address'], '10.200.{0}.254'.format(t['host_id']))
            health_data['cp_data']['zones'][zone]['hypervisors'][hv['id']] = tmp
        # if not quiet:
        #     #gotta unfuckulate this with the new abstructuration
        #     print 'Connectivity grid legend: (B# indicates Backup Server)'
        #     ids_list = [];
        #     for hv in HOSTS['ZONES'][zone]:
        #         if hv['hypervisor_type'] == 'backup':
        #             t = 'B{} - {} @ {}'
        #             ids_list.append('B{}'.format(hv['id']))
        #         else:
        #             t = ' {} - {} @ {}'
        #             ids_list.append('{}'.format(hv['id']))
        #         print t.format(hv['id'], hv['label'], hv['ip_address'])
        #     print
        #     row_f = '{:^5}' * ( len(HOSTS['ZONES'][zone] ) + 1 )
        #     print row_f.format('', *ids_list)
        #     trans = { 0 : ' {} '.format(FAIL), 1 : ' {} '.format(PASS) }
        #     # for n, hv in enumerate(health_data['cp_data']['zones']['hypervisors']['connectivity']['all']):
        #     #     tl = [ trans[bl] for bl in hv ]
        #     #     print row_f.format(ids_list[n], *tl)
        health_data['cp_data']['zones'][zone]['backup_servers'] = {};
        for bsid in HOSTS['ZONES'][zone]['BS'].itervalues():
            tmp = checkHVBSStatus(bsid)
            tmp['backups_data'] = checkBackups(bsid)
            tmp['ip_address'] = bsid['ip_address']
            tmp['label'] = bsid['label']
            tmp['cpu'] = cpuCheck(bsid['ip_address'])
            tmp['motherboard'] = motherboardCheck(hv['ip_address'])
            tmp['chassis'] = chassisCheck(hv['ip_address'])
            tmp['disks'] = diskHWCheck(hv['ip_address'])
            tmp['network_interfaces'] = interfaceCheck(hv['ip_address'])
            tmp['connectivity'] = {'storage_network':{}, 'all':{}}
            for t in HOSTS['ZONES'][zone]['HV'].itervalues():
                tmp['connectivity']['all'][t['id']] = checkHVConn(bsid['ip_address'], t['ip_address'])
            for t in HOSTS['ZONES'][zone]['BS'].itervalues():
                tmp['connectivity']['all']['B{0}'.format(t['id'])] = checkHVConn(bsid['ip_address'], t['ip_address'])
            if bsid['host_id']:
                for t in HOSTS['ZONES'][zone]['HV'].itervalues():
                    tmp['connectivity']['storage_network'][t['id']] = checkHVConn(bsid['ip_address'], '10.200.{0}.254'.format(t['host_id']))
                for t in HOSTS['ZONES'][zone]['BS'].itervalues():
                    tmp['connectivity']['storage_network']['B{0}'.format(t['id'])] = checkHVConn(bsid['ip_address'], '10.200.{0}.254'.format(t['host_id']))
            health_data['cp_data']['zones'][zone]['backup_servers'][bsid['id']] = tmp
            if not quiet:
                print fs.format('Label', tmp['label'])
                print fs.format('IP Address', tmp['ip_address'])
                print fs.format('Seen via', 'Ping:{0}, SSH:{1}, SNMP:{2}'.format( \
                    PASS if tmp['ping'] else FAIL, \
                    PASS if tmp['ssh'] else FAIL, \
                    PASS if tmp['snmp'] else FAIL))
                print fs.format('CPU Model', tmp['cpu']['model'])
                print fs.format('Cores', '{0} @ {1} MHz'.format(tmp['cpu']['cores'], tmp['cpu']['speed']))
                print fs.format('Kernel', tmp['kernel'])
                print fs.format('Distro', tmp['distro'])
                print fs.format('OnApp Version', tmp['version'])
                print fs.format('Memory', '{0} free / {1} MB'.format(tmp['freemem'], tmp['memory']))
                print fs.format('Loadavg', tmp['loadavg'])
                if len(tmp['backups_data']['zombie']) > 0:
                    print "Zombie Backups found: {0}".format(tmp['backups_data']['zombie'])
                if len(tmp['backups_data']['missing']) > 0:
                    print "Missing backups found: {0}".format(tmp['backups_data']['missing'])
                print '{0:-^45}'.format('')
        data_store_ids = dsql('SELECT dsj.data_store_id FROM data_store_joins dsj \
                               JOIN data_stores ds ON ds.id = dsj.data_store_id \
                               WHERE dsj.target_join_id=3 AND ds.enabled=1', unlist=False)
        if data_store_ids:
            health_data['cp_data']['zones'][zone]['data_stores'] = {}
            for dsid in data_store_ids:
                health_data['cp_data']['zones'][zone]['data_stores'][dsid] = checkDataStore(dsid)
        else: health_data['cp_data']['zones'][zone]['data_stores'] = {};
        if not quiet and data_store_ids:
            print "Datastores found: {0}".format(data_store_ids)
    tran_query = "SELECT \
        action, associated_object_type, associated_object_id, \
        created_at, started_at, updated_at \
      FROM transactions WHERE status='{0}' AND \
      created_at >= (CURDATE() - INTERVAL {1} DAY) \
      ORDER BY created_at"
    failed_trans=dpsql(tran_query.format("failed", TRANSACTION_DURATION), unlist=False)
    pending_trans=dpsql(tran_query.format("pending", TRANSACTION_DURATION), unlist=False)
    if pending_trans is False:
        pending_trans = [];
    if failed_trans is False:
        failed_trans = [];
    health_data['cp_data']['transactions'] = {}
    health_data['cp_data']['transactions']['pending'] = pending_trans;
    health_data['cp_data']['transactions']['failed'] = failed_trans;
    #print health_data;
    if VERBOSE or not API_TOKEN:
        print json.dumps(health_data, indent=2)
        print health_data
    logger(health_data)
    logger(json.dumps(health_data, indent=2))
    return health_data;

if __name__ == "__main__":
    health_data = mainFunction();
    if API_TOKEN:
        if PY_VER > (2, 7):
            response = apiCall('/api/healthcheck?token={0}'.format(API_TOKEN), data=health_data, method='POST', target=API_TARGET)
        elif PY_VER > (2, 6):
            response = apiCallForBadPython('/api/healthcheck?token={0}'.format(API_TOKEN), data=health_data, method='POST', target=API_TARGET)
        else:
            raise
        if 'success' not in response.keys():
            raise OnappException(response, 'apiCall', 'Success key was not found in response.')
        else:
            print 'View the healthcheck at: {0}/healthcheck/{1}'.format(API_TARGET, response['success']);
