#!/usr/bin/python2.7
import os
import ast
import ssl
import sys
import json
import shlex
import base64
import socket
import random
import inspect
import argparse
import datetime
import subprocess
import MySQLdb as SQL
# from subprocess import call, Popen
from copy import copy
from urllib2 import Request, urlopen, URLError, build_opener, HTTPHandler, HTTPError


ONAPP_ROOT = '/onapp'
ONAPP_CONF_DIR="{}/interface/config".format(ONAPP_ROOT);
ONAPP_CONF_FILE="{}/on_app.yml".format(ONAPP_CONF_DIR);
DB_CONF_FILE="{}/database.yml".format(ONAPP_CONF_DIR);
LOG_FILE="./test.log"


arp = argparse.ArgumentParser(prog='qualitycheck', description='Quality check for OnApp')
# arp.add_argument('-a', '--api', help='Enable API', action='store_true')
arp.add_argument('-v', '--verbose', help='Output more info while running', action='store_true', default=False)
arp.add_argument('-q', '--quiet', help='Don\'t output normal test output.', action='store_true', default=True)
arp.add_argument('-t', '--transactions', help='View N previous days of transactions, default: 7', type=int, metavar='N', default=7)
#arp.add_argument('-u', '--user', help='Perform API requests as user id N, default: 1', type=int, metavar='N', default=1)
arp.add_argument('-c', '--commands', help='Display commands for fixes, such as zombie disks or templates [BETA]', action='store_true')
arp.add_argument('-a', '--api', help='Hostname for API submission, default architecture.onapp.com', type=str, metavar='H', default='https://architecture.onapp.com')
arp.add_argument('-k', '--token', help='Token for sending data via API to architecture.onapp.com', type=str, metavar='K')
args = arp.parse_args();
VERBOSE=args.verbose;
#USER_ID=args.user;
USER_ID=1;
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
        print('OnappError, Action: {}, Data: {}'.format(self.f, self.d))
        if self.reason is not False: print('Reason: {}'.format(self.reason))

def logger(s):
    l = open(LOG_FILE, "a");
    text = '[{}] - {}\n'.format(str(datetime.datetime.now()),s)
    l.write(text)
    l.flush();
    l.close();

PASS="{}[+]{}".format(colors.fg.green, colors.reset)
FAIL="{}[-]{}".format(colors.fg.red, colors.reset)
CHCK="{}[?]{}".format(colors.fg.orange, colors.reset)

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
    if VERBOSE: logger("Running query:{}".format(' '.join(q.split())))
    db = dbConn();
    cur = db.cursor();
    cur.execute(q)
    res = [row for row in cur.fetchall()];
    num_fields = len(cur.description)
    cur.close();
    db.close();
    if len(res) == 1 and unlist:
        if len(res[0]) == 1: return res[0][0];
        else: return res[0]
    if len(res) == 0:
        return False
    if num_fields == 1:
        return [ t[0] for t in res ];
    return res;

dsql = dRunQuery;

#This is the shitty pretty version. Just leaving it in just to shame myself mainly.
def dRunPrettyQueryLegacy(fields, table, conditions=None):
    if type(fields) == str: fields = [fields];
    query = 'SELECT {} FROM {}'.format(','.join(fields), table);
    if not not conditions:
        query += ' WHERE {}'.format(conditions)
    db = dbConn();
    cur = db.cursor();
    cur.execute(query)
    res = cur.fetchall();
    num_fields = len(cur.description)
    field_names = [i[0] for i in cur.description]
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
    if VERBOSE: logger("Running pretty query:{}".format(' '.join(q.split())))
    db = dbConn();
    cur = db.cursor();
    cur.execute(q)
    res = cur.fetchall();
    num_fields = len(cur.description)
    field_names = [i[0] for i in cur.description]
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

def pullAPIKey():
    res = dsql("SELECT api_key FROM users WHERE id={}".format(USER_ID));
    if res == None:
        raise OnappException(res, 'pullAPIKey', 'API Key is not in database. \
        Please generate API key for user id {}, or specify a different user id.'.format(USER_ID));
    logger("Pulled API key from database.");
    return res;

def pullAPIEmail():
    res = dsql("SELECT email FROM users WHERE id={}".format(USER_ID));
    if res == None:
        raise OnappException(res, 'pullAPIEmail', 'Admin email is not in database. \
        Please fill in e-mail for user id {}, or specify a different user id.'.format(USER_ID));
    logger("Pulled API Email from database.");
    return res;

try:
    API_AUTH = base64.encodestring("{}:{}".format(pullAPIEmail(), pullAPIKey())).replace('\n', '');
except OnAppException:
    API_AUTH = None

def apiCall(r, data=None, method='GET', target=API_TARGET, auth=API_AUTH):
    req = Request("{}{}".format(target, r), json.dumps(data))
    req.add_header("Authorization", "Basic {}".format(auth))
    req.add_header("Accept", "application/json")
    req.add_header("Content-type", "application/json")
    if method: req.get_method = lambda: method;
    if target.startswith('https://'):
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        ssl_content.load_default_certs();
        response = urlopen(req, context=ssl_context)
    else:
        response = urlopen(req)
    status = response.getcode()
    caller = inspect.stack()[1][3];
    logger('API Call executed - {}{}, Status code: {}'.format(target, r, status));
    if VERBOSE: print('API Call executed - {}{}, Status code: {}'.format(target, r, status))
    if status == 200:
        return ast.literal_eval(response.read().replace('null', 'None').replace('true', 'True').replace('false', 'False')) or True;
    elif status == 204:
        return True;
    elif status == 201:
        return True;
    elif status == 400:
        raise OnappException("400: Bad request", caller);
    elif status == 403:
        raise OnappException("403: Unauthorized API Call", caller)
    elif status == 404:
        raise OnappException("404: Requested URL {} Not Found".format(r), caller)
    elif status == 422:
        raise OnappException("422: Erroneous parameters in data", caller, str(data))
    elif status == 500:
        raise OnappException("500: Internal server error. Investigate logs on control server.", caller)
    elif status == 503:
        raise OnappException("503: System loaded, request will process when it can.", caller)
    else:
        raise OnappException("{}: Unknown HTTP Status code", caller)

def storageAPICall(target, r, data=None, method=None):
    req = Request("http://{}:8080{}".format(target, r), data)
    if method: req.get_method = lambda: method;
    response = urlopen(req)
    status = response.getcode()
    #caller = inspect.stack()[1][3];
    #print 'API Call executed - {}{}, Status code: {}'.format(API_TARGET, r, status);
    return ast.literal_eval(response.read().replace('null', 'None').replace('true', 'True').replace('false', 'False'));

stapi = storageAPICall;

HOSTS={'IS':{}, 'ALL':{}, 'ZONES':{}}

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

for zid in dsql("SELECT DISTINCT p.id FROM packs AS p \
                 JOIN hypervisors AS hv ON hv.hypervisor_group_id=p.id \
                 WHERE p.type='HypervisorGroup' \
                 GROUP BY p.id \
                 HAVING count(hv.id) > 0;", unlist=False):
    HOSTS['ZONES'][zid] = dpsql("SELECT label FROM packs WHERE id={}".format(zid), unlist=False)
    HOSTS['ZONES'][zid]['HV'] = {}
    for hvid in dsql("SELECT id FROM hypervisors WHERE hypervisor_group_id={} AND enabled=1".format(zid), unlist=False):
        HOSTS['ZONES'][zid]['HV'][hvid] = dpsql( \
            "SELECT id, host_id, label, ip_address, hypervisor_type \
             FROM hypervisors WHERE id={}".format(hvid) )
    bsids = dsql("SELECT id FROM backup_server_joins WHERE \
        target_join_type='HypervisorGroup' AND target_join_id={}".format(zid), unlist=False)
    HOSTS['ZONES'][zid]['BS'] = {};
    if bsids:
        for bsid in bsids:
            HOSTS['ZONES'][zid]['BS'][bsid] = dpsql("SELECT id, label, ip_address, 'backup' as hypervisor_type \
                FROM backup_servers WHERE id={}".format(bsid));
            HOSTS['ZONES'][zid]['BS'][bsid]['host_id'] = dsql("SELECT host_id FROM hypervisors WHERE ip_address='{}'" \
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


def runCmd(cmd, shell=False, shlexy=True):
    if shlexy and type(cmd) is str:
        cmd = shlex.split(cmd)
    stdout, stderr = subprocess.Popen(cmd, shell=shell, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate();
    if stderr: logger("Command {} failed, stderr: {}".format(cmd, stderr.strip()))
    return stdout.strip();

def checkHVBSStatus(target):
    rData = {};
    vm_list = [];
    hv_ver_bash_cmd = "ssh -p{} root@{} \"cat /onapp/onapp-store-install.version 2>/dev/null || cat /onapp/onapp-hv-tools.version 2>/dev/null || grep Version /onappstore/package-version.txt 2>/dev/null || echo '???'\""
    hv_ver_cmd = [ 'su', 'onapp', '-c', hv_ver_bash_cmd.format(ONAPP_CONFIG['ssh_port'], target['ip_address']) ]
    hv_kernel_cmd = [ 'su', 'onapp', '-c', 'ssh -p{} root@{} "uname -r 2>/dev/null" 2>/dev/null'.format(ONAPP_CONFIG['ssh_port'], target['ip_address']) ]
    hv_distro_cmd = [ 'su', 'onapp', '-c', 'ssh -p{} root@{} "cat /etc/redhat-release 2>/dev/null" 2>/dev/null'.format(ONAPP_CONFIG['ssh_port'], target['ip_address']) ]
    rData['version'] = runCmd(hv_ver_cmd);
    rData['kernel'] = runCmd(hv_kernel_cmd);
    rData['distro'] = runCmd(hv_distro_cmd);
    rData['loadavg'] = runCmd(['su','onapp','-c','ssh -p{} root@{} "cat /proc/loadavg"'.format(ONAPP_CONFIG['ssh_port'], target['ip_address'])])
    rData['memory'] = runCmd(['su','onapp','-c','ssh -p{} root@{} "free -m"'.format(ONAPP_CONFIG['ssh_port'], target['ip_address'])]).split('\n')[1].split()[1]
    rData['freemem'] = runCmd(['su','onapp','-c','ssh -p{} root@{} "free -m"'.format(ONAPP_CONFIG['ssh_port'], target['ip_address'])]).split('\n')[1].split()[2]
    hv_vms = dsql("SELECT identifier FROM virtual_machines WHERE hypervisor_id = {} AND booted=1 AND identifier IS NOT NULL".format(target['id']), False)
    if hv_vms is False:
        hv_vms = [];
    if target['hypervisor_type'] == 'kvm':
        vm_from_hv = runCmd(['su','onapp','-c','ssh -p{} root@{} "virsh list --state-running"'.format(ONAPP_CONFIG['ssh_port'], target['ip_address'])])
        vm_list = vm_from_hv.split('\n')
        del vm_list[0]
        del vm_list[0]
        vm_list = [ t.split()[1] for t in vm_list if "STORAGENODE" not in t.split()[1] ]
    if target['hypervisor_type'] == 'xen':
        vm_from_hv = runCmd(['su','onapp','-c','ssh -p{} root@{} "xm list --state=running"'.format(ONAPP_CONFIG['ssh_port'], target['ip_address'])])
        vm_list = vm_from_hv.split('\n')
        del vm_list[0]
        vm_list = [ x for x in vm_list if 'Domain-0' not in x ]
        vm_list = [ t.split()[0] for t in vm_list if "STORAGENODE" not in t.split()[1] ]
    cloned_hvvms = copy(hv_vms)
    zombie_vms = [];
    for vm in vm_list:
        try:
            cloned_hvvms.remove(vm)
        except ValueError:
            print('!!! Virtual Machine {} is booted on the hypervisor but not booted in database !!!'.format(vm))
            logger('! Virtual Machine {} is bootedon the hypervisor but not booted in database'.format(vm))
            zombie_vms.append(vm)
    if len(cloned_hvvms) > 0:
        print '!!! Virtual machines found running in database, but not on the hypervisor: ', ','.join(cloned_hvvms)
        logger('! Virtual machines found running in database, but not on the hypervisor: {}'.format(','.join(cloned_hvvms)))
    if len(zombie_vms): rData['zombie_vms'] = zombie_vms;
    if len(cloned_hvvms): rData['dead_vms'] = cloned_hvvms;
    #### Create also for xen hypervisors...
    return rData;

def checkHVConn(from_ip, to_ip):
    cmd = "ssh -p{} root@{} 'ping -w1 {}'".format(ONAPP_CONFIG['ssh_port'], from_ip, to_ip)
    rData = runCmd(shlex.split(cmd))
    return 0 if rData == '' else 1

def checkNetJoins(zone_id):
    network_ids = dsql("SELECT network_id FROM networking_network_joins WHERE target_join_id={}".format(zone_id), unlist=False)
    if network_ids is False: return False
    labels = [];
    for nid in network_ids:
        network_label = dsql("SELECT label FROM networking_networks WHERE id={}".format(nid))
        labels.append(network_label)
    return labels;

def checkDataJoins(zone_id):
    datazone_ids = dsql("SELECT data_store_id FROM data_store_joins WHERE target_join_id={}".format(zone_id), unlist=False)
    if datazone_ids is False: return False
    labels = [];
    for dzid in datazone_ids:
        datazone_label = dsql("SELECT label FROM data_stores WHERE id={}".format(dzid))
        labels.append(datazone_label)
    return labels;

def checkBackupJoins(zone_id):
    backup_ids = dsql("SELECT backup_server_id FROM backup_server_joins WHERE target_join_id={}".format(zone_id), unlist=False)
    if backup_ids is False: return False
    labels = [];
    for bsid in backup_ids:
        backup_label = dsql("SELECT label FROM backup_servers WHERE id={}".format(bsid))
        labels.append(backup_label)
    return labels;

def checkComputeZones(zone_id=False):
    zone_data = {};
    zone_ids = HOSTS['ZONES'].keys();
    if zone_id is False and type(zone_ids) is not long:
        all_zone_ids = dsql("SELECT id FROM packs WHERE type='HypervisorGroup'")
        for zid in all_zone_ids:
            vc_check = dsql("SELECT hypervisor_type FROM hypervisors WHERE hypervisor_group_id={} AND hypervisor_type NOT IN ('vcenter','vcloud')".format(zid))
            if vc_check is False: continue
            zone_data[zid] = {'zone_id': zid, 'label':HOSTS['ZONES'][zid]['label'], 'network_joins':checkNetJoins(zid), \
                'data_store_joins':checkDataJoins(zid), 'backup_server_joins':checkBackupJoins(zid)}
    elif type(zone_id) is list:
        for zid in zone_id:
            vc_check = dsql("SELECT hypervisor_type FROM hypervisors WHERE hypervisor_group_id={} AND hypervisor_type NOT IN ('vcenter','vcloud')".format(zid))
            if len(vc_check) == 0: continue
            zone_data[zid] = {'zone_id':zid, 'label':HOSTS['ZONES'][zid]['label'], 'network_joins':checkNetJoins(zid), \
                'data_store_joins':checkDataJoins(zid), 'backup_server_joins':checkBackupJoins(zid)}
    else:
        if type(zone_ids) is long: zone_id = zone_ids;
        vc_check = dsql("SELECT hypervisor_type FROM hypervisors WHERE hypervisor_group_id={} AND hypervisor_type NOT IN ('vcenter','vcloud')".format(zone_id))
        if len(vc_check) == 0: raise OnappException('Requested hypervisor zone either does not exist or is all vcenter/vcloud')
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
    rData['model'] = runCmd(['su', 'onapp', '-c', 'ssh -p{} root@{} "{}"'.format(ONAPP_CONFIG['ssh_port'], target, cpu_model_cmd)])
    rData['speed'] = runCmd(['su', 'onapp', '-c', 'ssh -p{} root@{} "{}"'.format(ONAPP_CONFIG['ssh_port'], target, cpu_speed_cmd)])
    rData['cores'] = runCmd(['su', 'onapp', '-c', 'ssh -p{} root@{} "{}"'.format(ONAPP_CONFIG['ssh_port'], target, cpu_cores_cmd)])
    return rData;


#def checkISHealth(ds_data):


def checkDataStore(target_id):
    logger("Checking data store id ={}".format(target_id))
    if VERBOSE: print "Checking data store id {}".format(target_id)
    ds_data = dpsql("SELECT id, label, identifier, local_hypervisor_id, data_store_size, hypervisor_group_id, \
        integrated_storage_cache_enabled as is_cache_enabled, integrated_storage_cache_settings as is_cache_settings, \
        io_limits, data_store_type FROM data_stores WHERE id={}".format(target_id))
    disk_count = dpsql("SELECT count(*) FROM disks WHERE built=1 AND data_store_id={}".format(target_id))
    db_disk_ids = dsql("SELECT identifier FROM disks WHERE data_store_id={} AND built=1".format(target_id))
    ds_data['disk_count'] = disk_count;
    hv_id = dsql("SELECT target_join_id FROM data_store_joins WHERE data_store_id=1 AND target_join_type='HypervisorGroup'")
    # The HV_ID should never return a list because data stores should only be able to be joined to one zone at a time.
    # zombie disks
    if ds_data['data_store_type'] == 'lvm':
        if ds_data['local_hypervisor_id'] is not None:
            target_ip = dsql("SELECT ip_address FROM hypervisors WHERE id={}".format(ds_data['local_hypervisor_id']))
            if VERBOSE: print("Using local hypervisor at {}".format(target_ip))
            logger("Using local hypervisor at {}".format(target_ip))
        else:
            target_ip = dsql("SELECT ip_address FROM hypervisors WHERE hypervisor_group_id={} LIMIT 1".format(ds_data['hypervisor_group_id']))
            if VERBOSE: print("Using first hypervisor at {} from group id {}".format(target_ip, ds_data['hypervisor_group_id']))
            logger("Using first hypervisor at {} from group id {}".format(target_ip, ds_data['hypervisor_group_id']))
        lvs_output = runCmd(['su', 'onapp', '-c', 'ssh -p{} root@{} "lvs {} --noheadings"'.format(ONAPP_CONFIG['ssh_port'], target_ip, ds_data['identifier'])])
        lv_disks = [line.split()[0] for line in lvs_output];
        logger("Adding all LVM disk sizes together. ")
        if VERBOSE: print "Adding all LVM disk sizes together"
        lv_sizes = [ float(n) for n in runCmd("lvs -o LV_SIZE --noheadings --units g --nosuffix").split() ]
        lv_size_sum = sum(lv_sizes)
        if VERBOSE: print "Total size: {}g".format(lv_size_sum)
        logger("Total size: {}g".format(lv_size_sum))
        for disk in db_disk_ids:
            try:
                lv_disks.remove(disk)
            except ValueError:
                print('!!! Disk {} found in database is NOT in LVM data store {} !!!'.format(disk, ds_data['identifier']))
                logger('! Missing disk {} is in database but not in LVM data store {}'.format(disk, ds_data['identifier']))
        if len(lv_disks) > 0:
            print ' !!! Zombie disks found:', ','.join(lv_disks)
            logger('! Zombie disks found: '+','.join(lv_disks))
            if DISPLAY_COMMANDS:
                print 'Displaying removal commands for zombie disks: '
                for disk in lv_disks:
                    print 'rm -f /dev/{}/{}'.format(ds_data['identifier'], disk)
        ds_data['zombie_disks'] = lv_disks;
        ds_data['hv_disk_size_total'] = lv_size_sum;
    if ds_data['data_store_type'] == 'is':
        target_ip = dsql("SELECT ip_address FROM hypervisors WHERE hypervisor_group_id={} \
            AND host_id IS NOT NULL LIMIT 1".format(ds_data['hypervisor_group_id']))
        is_ds = stapi(target=target_ip,r='/is/Datastore/{}'.format(ds_data['identifier']))[ds_data['identifier']]
        is_disks = is_ds['vdisks'].split(',')
        node_sizes = {}
        for node in is_ds['members'].split(','):
            tmp = stapi(target_ip, '/is/Node/{}'.format(node))[node]['utilization']
            node_sizes = { node : tmp }
        ds_data['average_node_usage'] = (sum(node_sizes.values())/len(node_sizes))
        for disk in db_disk_ids:
            try:
                is_disks.remove(disk)
            except ValueError:
                print('{}!!! Disk {} found in database is NOT in IS data store {} !!!{}'.format( \
                    colors.fg.red, disk, ds_data['identifier'], colors.none))
                logger('! Missing disk {} is in database but not in IS data store {}'.format(disk, ds_data['identifier']))
        if len(is_disks) > 0:
            print ' !!! Zombie disks found:', ','.join(is_disks)
            logger('! Zombie disks found: '+','.join(is_disks))
            if DISPLAY_COMMANDS:
                print 'Displaying removal commands for zombie disks(check that these disks are not mounted first): '
                for disk in is_disks:
                    print 'onappstore offline uuid={}'.format(disk)
                for disk in is_disks:
                    print 'onappstore remove uuid={}'.format(disk)
        ds_data['zombie_disks'] = is_disks;
        ds_data['data_store_size'] = ((is_ds['total_usable_size']/1024.0)/1024.0)/1024.0
        #ds_data['is_health'] = checkISHealth(ds_data)
    ds_data['db_disk_size_total'] = int(dsql("SELECT SUM(disk_size) FROM disks WHERE data_store_id={} AND built=1".format(ds_data['id'])))
    return ds_data;

def checkBackups(target):
    data = {'missing':[], 'zombie':[]};
    # go through one backup server and check the backups with those in the database.
    bs_data = dpsql("SELECT id, ip_address, capacity FROM backup_servers WHERE id={}".format(target))
    backups_in_db = dsql("SELECT identifier FROM backups WHERE backup_server_id={}".format(target))
    backups_on_server_fullpath = runCmd(['su', 'onapp', '-c', 'ssh -p{} root@{} "ls -d -1 {}/[a-z]/[a-z]/*"'.format(ONAPP_CONFIG['ssh_port'], bs_data['ip_address'], ONAPP_CONFIG['backups_path'])]).split('\n')
    backups_on_server = [line.lstrip(ONAPP_CONFIG['backups_path']).lstrip('/').split('/')[2] for line in backups_on_server_fullpath]
    for backup in backups_in_db:
        try:
            backups_on_server.remove(backup);
        except ValueError:
            print('{}!!! Backup found in database but not on disk at {}/{}/{}/{} on backup server {}{}'.format( \
                colors.fg.red, ONAPP_CONFIG['backups_path'], backup[0], backup[1], backup, colors.none))
            logger('!!! Backup found in database but not on disk at {}/{}/{}/{} on backup server {}'.format( \
                ONAPP_CONFIG['backups_path'], backup[0], backup[1], backup))
            data['missing'].append(backup)
    if len(backups_on_server) > 0:
        print(colors.fg.yellow, '!!! Zombie backups found: ', ','.join(backups_on_server), colors.fg.none)
        logger('!!! Zombie backups found: ', ','.join(backups_on_server))
        if DISPLAY_COMMANDS:
            print 'Displaying removal commands for zombie backups: '
            for backups in backups_on_server:
                print 'rm -rf {}/{}/{}/{}'.format(ONAPP_CONFIG['backups_path'], backup[0], backup[1], backup)
    data['zombie'] = backups_on_server;
    # maybe have it come check disk space vs the database sizes to find "empty" backups?
    backup_sizes_in_db = { t[0] : t[1] for t in dsql("SELECT identifier, backup_size FROM backups WHERE backup_server_id={}".format(target)) }
    inc_backups_by_vm = {}
    inc_backups_in_db = dsql('SELECT identifier, target_id FROM backups WHERE \
            type="BackupIncremental" AND target_type="VirtualMachine" AND backup_server_id={} \
            ORDER BY created_at'.format(target))
    for vm in inc_backups_in_db:
        if vm[1] not in inc_backups_by_vm.keys():
            inc_backups_by_vm[vm[1]] = [vm[0]]
        else:
            inc_backups_by_vm[vm[1]].append(vm[0])
    for vm in inc_backups_by_vm.keys():
        tmp = [ '{}/{}/{}/{}'.format(ONAPP_CONFIG['backups_path'], b[0], b[1], b) for b in inc_backups_by_vm[vm]]
        server_blist = runCmd(['su', 'onapp', '-c', 'ssh -p{} root@{} "du -sk {}"'.format(ONAPP_CONFIG['ssh_port'], bs_data['ip_address'], ' '.join(tmp))]).split('\n')
        backup_sizes_on_server = { t.split('\t')[1].split('/')[-1] : int(t.split('\t')[0]) for t in server_blist }
    norm_backups_in_db = dsql('SELECT identifier, target_id FROM backups WHERE \
            backup_server_id={} AND type="BackupNormal"'.format(target))
    tmp = [ '{}/{}/{}/{}'.format(ONAPP_CONFIG['backups_path'], b[0], b[1], b) for b in norm_backups_in_db ]
    for path in tmp:
        server_du = runCmd(['su', 'onapp', '-c', 'ssh -p{} root@{} "du -sk {}"'.format(ONAPP_CONFIG['ssh_port'], bs_data['ip_address'], path)]).split('\t')
        backup_sizes_on_server[server_du[1]] = server_du[0]
    #for backups in backup_sizes_in_db.keys():
        #go through each one, compare it to the values I got previously, report differences.
    return data

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
        'cpu' : cpuCheck()}
    health_data['cp_data']['vm_data'] = { \
        'off' : dsql('SELECT count(*) AS count FROM virtual_machines WHERE booted=0') ,\
        'on' : dsql('SELECT count(*) AS count FROM virtual_machines WHERE booted=1') ,\
        'failed' : dsql('SELECT count(*) AS count FROM virtual_machines WHERE state="failed"') }
    health_data['cp_data']['zones'] = checkComputeZones();
    if not quiet:
        fs = '{:>20s} : {}'
        print fs.format('Version', health_data['cp_data']['version'])
        print fs.format('Kernel', health_data['cp_data']['kernel'])
        print fs.format('Distribution', health_data['cp_data']['distro'])
        print fs.format('RAM', health_data['cp_data']['memory'])
        print fs.format('Free RAM', health_data['cp_data']['freemem'])
        print fs.format('Load Average', health_data['cp_data']['loadavg'])
        print fs.format('Timezone', health_data['cp_data']['timezone'])
        print fs.format('CPU Model', health_data['cp_data']['cpu']['model'])
        print '{:>20s} : {} MHz'.format('CPU Speed', health_data['cp_data']['cpu']['speed'])
        print fs.format('CPU Cores', health_data['cp_data']['cpu']['cores'])
        print fs.format('Total VMs ON / OFF', '{} / {}'.format( \
            health_data['cp_data']['vm_data']['off'], health_data['cp_data']['vm_data']['on']))
        if health_data['cp_data']['vm_data']['failed'] is not False:
            print fs.format('Total VMs FAIL', health_data['cp_data']['vm_data']['failed'])
        print '{:-^45}'.format('')
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    for zone in health_data['cp_data']['zones'].keys():
        health_data['cp_data']['zones'][zone]['hypervisors'] = {}
        for hv in HOSTS['ZONES'][zone]['HV'].itervalues():
            ## it seems like the first SNMP connection would register 0, then give a good value afterwards
            ## so... gonna prime it just in case:
            primer = sock.connect_ex((hv['ip_address'], 161))
            del primer;
            tmp = checkHVBSStatus(hv)
            tmp['id'] = hv['id']
            tmp['type'] = hv['hypervisor_type']
            tmp['ip_address'] = hv['ip_address']
            tmp['label'] = hv['label']
            tmp['cpu'] = cpuCheck(hv['ip_address'])
            tmp['vm_data'] = { \
                'off' : dsql('SELECT count(*) AS count FROM virtual_machines \
                              WHERE booted=0 AND hypervisor_id={}'.format(hv['id'])) ,\
                'on' : dsql('SELECT count(*) AS count FROM virtual_machines \
                             WHERE booted=1 AND hypervisor_id={}'.format(hv['id'])) ,\
                'failed' : dsql('SELECT count(*) AS count FROM virtual_machines \
                                 WHERE state="failed" AND hypervisor_id={}'.format(hv['id'])) }
            tmp['connectivity'] = {'storage_network':{}, 'all':{}}
            ping_cmd = [ 'ping', hv['ip_address'], '-w1' ]
            ssh_cmd = [ 'su',  'onapp',  '-c', "ssh -p{} root@{} \'echo connected\'".format(ONAPP_CONFIG['ssh_port'], hv['ip_address']) ]
            tmp['connectivity']['ping'] = 0 if runCmd(ping_cmd) == '' else 1;
            tmp['connectivity']['ssh'] = 0 if runCmd(ssh_cmd) == '' else 1;
            tmp['connectivity']['snmp'] = 0 if sock.connect_ex((hv['ip_address'], 161)) == 0 else 1;
            if not quiet:
                #print all the hypervisor data
                fs = '{:>20s} : {}'
                if hv['hypervisor_type'] == 'backup': print 'Backup Server ID {}'.format(tmp['id'])
                else: print 'Hypervisor ID {}'.format(tmp['id'])
                print fs.format('Label', tmp['label'])
                print fs.format('IP Address', tmp['ip_address'])
                print fs.format('Seen via', 'Ping:{}, SSH:{}, SNMP:{}'.format( \
                    PASS if tmp['ping'] else FAIL, \
                    PASS if tmp['ssh'] else FAIL, \
                    PASS if tmp['snmp'] else FAIL))
                print fs.format('CPU Model', tmp['cpu']['model'])
                print fs.format('Cores', '{} @ {} MHz'.format(tmp['cpu']['cores'], tmp['cpu']['speed']))
                print fs.format('Kernel', tmp['kernel'])
                print fs.format('Distro', tmp['distro'])
                print fs.format('OnApp Version', tmp['version'])
                print fs.format('Memory', '{} free / {} MB'.format(tmp['freemem'], tmp['memory']))
                print fs.format('Loadavg', tmp['loadavg'])
                print fs.format('Total VMs ON / OFF', '{} / {}'.format(tmp['vm_data']['on'], tmp['vm_data']['off']))
                if tmp['vm_data']['failed'] > 0:
                    print fs.format('Total VMs FAILED', tmp['vm_data']['failed'])
                if 'zombie_vms' in tmp.keys():
                    print fs.format('Zombie VMs', ','.join(tmp['zombie_vms']))
                print '{:-^45}'.format('')
            for t in HOSTS['ZONES'][zone]['HV'].itervalues():
                tmp['connectivity']['all'][t['id']] = checkHVConn(hv['ip_address'], t['ip_address'])
            for t in HOSTS['ZONES'][zone]['BS'].itervalues():
                tmp['connectivity']['all']['B{}'.format(t['id'])] = checkHVConn(hv['ip_address'], t['ip_address'])
            if hv['host_id']:
                for t in HOSTS['ZONES'][zone]['HV'].itervalues():
                    tmp['connectivity']['storage_network'][t['id']] = checkHVConn(hv['ip_address'], '10.200.{}.254'.format(t['host_id']))
                for t in HOSTS['ZONES'][zone]['BS'].itervalues():
                    tmp['connectivity']['storage_network']['B{}'.format(t['id'])] = checkHVConn(hv['ip_address'], '10.200.{}.254'.format(t['host_id']))
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
            tmp['ip_address'] = bsid['ip_address']
            tmp['label'] = bsid['label']
            tmp['cpu'] = cpuCheck(bsid['ip_address'])
            tmp['connectivity'] = {'storage_network':{}, 'all':{}}
            for t in HOSTS['ZONES'][zone]['HV'].itervalues():
                tmp['connectivity']['all'][t['id']] = checkHVConn(bsid['ip_address'], t['ip_address'])
            for t in HOSTS['ZONES'][zone]['BS'].itervalues():
                tmp['connectivity']['all']['B{}'.format(t['id'])] = checkHVConn(bsid['ip_address'], t['ip_address'])
            if bsid['host_id']:
                for t in HOSTS['ZONES'][zone]['HV'].itervalues():
                    tmp['connectivity']['storage_network'][t['id']] = checkHVConn(bsid['ip_address'], '10.200.{}.254'.format(t['host_id']))
                for t in HOSTS['ZONES'][zone]['BS'].itervalues():
                    tmp['connectivity']['storage_network']['B{}'.format(t['id'])] = checkHVConn(bsid['ip_address'], '10.200.{}.254'.format(t['host_id']))
            health_data['cp_data']['zones'][zone]['backup_servers'][bsid['id']] = tmp
        data_store_ids = dsql('SELECT dsj.data_store_id FROM data_store_joins dsj \
                               JOIN data_stores ds ON ds.id = dsj.data_store_id \
                               WHERE dsj.target_join_id=3 AND ds.enabled=1', unlist=False)
        health_data['cp_data']['zones'][zone]['data_stores'] = { dsid : checkDataStore(dsid) for dsid in data_store_ids }
    if not quiet: print

    tran_query = "SELECT \
        action, associated_object_type, associated_object_id, \
        created_at, started_at, updated_at, log_output \
      FROM transactions WHERE status='{}' AND \
      created_at >= (CURDATE() - INTERVAL {} DAY) \
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
    if VERBOSE or not API_TOKEN: print json.dumps(health_data, indent=2)
    logger(health_data)
    logger(json.dumps(health_data, indent=2))

if __name__ == "__main__":
    mainFunction();
    if API_TOKEN:
        response = apiCall('/api/healthcheck?token={}'.format(API_TOKEN), data=json.dumps(health_data), method='POST', target=API_TARGET)
        if 'success' not in response.keys():
            raise OnappException(response, 'apiCall', 'Success key was not found in response.')
        else:
            print 'View the healthcheck at: {}/healthcheck/{}'.format(API_TARGET, response['success']);
