import os
import sys
import json
import shlex
import random
import argparse
import subprocess
import MySQLdb as SQL
# from subprocess import call, Popen
from datetime import datetime


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
    text = '[{}] - {}\n'.format(str(datetime.now()),s)
    l.write(text)
    l.flush();
    l.close();

PASS="{}[+]{}".format(colors.fg.green, colors.reset)
FAIL="{}[-]{}".format(colors.fg.red, colors.reset)
CHCK="{}[?]{}".format(colors.fg.orange, colors.reset)

# arp = argparse.ArgumentParser(prog='qualitycheck', description='Quality check script for OnApp')
# arp.add_argument("-p", "--pdf", help="Process data to PDF", default="http://zack.grindall")
# arp.add_argument("-a", "--api", help="Enable API checks", action="store_true")
# arp.add_argument("-h", "--hardware", help="Only hardware checks", action="store_true")
# arp.add_argument("-d", "--onappdir", help="Onapp Root Directory(default /onapp)", default="/onapp")
# args = arp.parse_args();
# API_ENABLED=args.api;
# HARDWARE_ONLY=args.hardware;
# ONAPP_ROOT=args.onappdir;

ONAPP_ROOT = '/onapp'

ONAPP_CONF_DIR="{}/interface/config".format(ONAPP_ROOT);
ONAPP_CONF_FILE="{}/on_app.yml".format(ONAPP_CONF_DIR);
DB_CONF_FILE="{}/database.yml".format(ONAPP_CONF_DIR);

LOG_FILE="./test.log"

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

def dbConn(conf=None):
    if conf is None:
        conf = DB_CONFIG[DB_CONFIG['onapp_daemon']];
    return SQL.connect(host=conf['host'], user=conf['username'], passwd=conf['password'], db=conf['database'])

def dRunQuery(q, unlist=True):
    db = dbConn();
    cur = db.cursor();
    cur.execute(q)
    res = cur.fetchall();
    cur.close();
    db.close();
    if len(res) == 1 and unlist:
        if len(res[0]) == 1: return res[0][0];
        else: return res[0]
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
            o[fld] = res[n][nn];
        output.append(o)
    if len(output) == 1: return output[0]
    return output;

def dRunPrettyQuery(q):
    db = dbConn();
    cur = db.cursor();
    cur.execute(q)
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
            o[fld] = res[n][nn];
        output.append(o)
    if len(output) == 1: return output[0]
    return output;


dpsql = dRunPrettyQuery;

def pullAPIKey():
    res = dsql("SELECT api_key FROM users WHERE id=1");
    if res == None:
        print('API Key is not in database. Skipping API functions');
        API_ENABLED=False;
    logger("Pulled API key from database.");
    return res;

def pullAPIEmail():
    res = dsql("SELECT email FROM users WHERE id=1");
    if res == None:
        print('Admin email was not able to be pulled. Skipping API functions.);
        API_ENABLED=False;
    logger("Pulled API Email from database.");
    return res;

if API_ENABLED:
    API_AUTH = base64.encodestring("{}:{}".format(pullAPIEmail(), pullAPIKey())).replace('\n', '');
else: API_AUTH=False;

def apiCall(r, data=None, method=None, target=None, auth=None):
    if auth is None: auth = API_AUTH;
    if target is None: target = API_TARGET;
    req = Request("{}{}".format(target, r), json.dumps(data))
    req.add_header("Authorization", "Basic {}".format(auth))
    req.add_header("Accept", "application/json")
    req.add_header("Content-type", "application/json")
    if method: req.get_method = lambda: method;
    response = urlopen(req)
    status = response.getcode()
    caller = inspect.stack()[1][3];
    logger('API Call executed - {}{}, Status code: {}'.format(target, r, status));
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

IS_HOST_INFO=dpsql( \
"SELECT host_id, ip_address, label FROM \
  (SELECT id, host_id, label, ip_address, 1 AS row_order \
  FROM hypervisors \
  WHERE hypervisor_type IN ('kvm','xen') \
  AND ip_address IS NOT NULL \
  AND host_id IS NOT NULL \
  AND enabled=1 AND ip_address NOT IN \
    (SELECT ip_address FROM backup_servers WHERE ip_address IS NOT NULL) \
  UNION  \
  SELECT id, host_id, label, ip_address, 2 AS row_order \
  FROM hypervisors \
  WHERE ip_address IS NOT NULL \
  AND host_id IS NOT NULL \
  AND enabled=1 AND ip_address IN \
    (SELECT ip_address FROM backup_servers WHERE ip_address IS NOT NULL) \
  ORDER BY row_order, id) AS T")
# IS_HOSTIDS=dsql("SELECT host_id FROM (SELECT id, host_id, ip_address, 1 AS row_order FROM hypervisors WHERE hypervisor_type IN ('kvm','xen') AND ip_address IS NOT NULL AND host_id IS NOT NULL AND enabled=1 AND ip_address NOT IN (SELECT ip_address FROM backup_servers WHERE ip_address IS NOT NULL) UNION SELECT id, host_id, ip_address, 2 AS row_order FROM hypervisors WHERE ip_address IS NOT NULL AND host_id IS NOT NULL AND enabled=1 AND ip_address IN (SELECT ip_address FROM backup_servers) ORDER BY row_order, id) AS T")
# IS_LABELS=dsql("SELECT label FROM (SELECT id, label, ip_address, 1 AS row_order FROM hypervisors WHERE hypervisor_type IN ('kvm','xen') AND ip_address IS NOT NULL AND host_id IS NOT NULL AND enabled=1 AND ip_address NOT IN (SELECT ip_address FROM backup_servers WHERE ip_address IS NOT NULL) UNION SELECT id, label, ip_address, 2 AS row_order FROM hypervisors WHERE ip_address IS NOT NULL AND host_id IS NOT NULL AND enabled=1 AND ip_address IN (SELECT ip_address FROM backup_servers) ORDER BY row_order, id) AS T")
HOST_INFO=dpsql( \
"SELECT id, label, ip_address FROM ( \
  SELECT id, label, ip_address, 1 AS row_order \
  FROM hypervisors \
  WHERE hypervisor_type IN ('kvm','xen') \
  AND ip_address IS NOT NULL \
  AND enabled=1 AND ip_address NOT IN \
    (SELECT ip_address FROM backup_servers WHERE ip_address IS NOT NULL) \
  UNION \
  SELECT id, label, ip_address, 2 AS row_order \
  FROM backup_servers \
  WHERE ip_address IS NOT NULL  \
  AND enabled=1 \
  ORDER BY row_order, id) AS T")
# LABELS=dsql("SELECT label FROM (SELECT id, label, ip_address, 1 AS row_order FROM hypervisors WHERE hypervisor_type IN ('kvm','xen') AND ip_address IS NOT NULL AND enabled=1 AND ip_address NOT IN (SELECT ip_address FROM backup_servers WHERE ip_address IS NOT NULL) UNION SELECT id, label, ip_address, 2 AS row_order FROM backup_servers WHERE ip_address IS NOT NULL AND enabled=1 ORDER BY row_order, id) AS T")

# checkallHVandBS
# checkallHVconn
# checkISconn
# checkNetZones
# checkDataZones
# checkComputeZones
# createDestroyVM
# cpVersion
# hvVersion
# timeZoneCheck
# resourceCheck
# checkHVHW
# rootDiskSize
# checkTransactions
# checkAllLoadAvg
def runCmd(cmd):
    if type(cmd) is str:
        cmd = shlex.split(cmd)
    stdout, stderr = subprocess.Popen(cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate();
    # maybe check for stderr here?
    return stdout;

def checkAllHVBS():


    # cmd = [ TEST_RB , 'test=destroy_hypervisor' ];
    # cmd.append('mac='+mgt_mac);
    #
    # p = Popen(cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE);
    # stdo, stde = p.communicate();


def checkHVBSStatus(target):
    # ping, ssh, SNMP, version, kernel, distro
    rData = {};
    ping_cmd = [ 'ping', target, '-w1' ]
    ssh_cmd = [ 'su',  'onapp',  '-c', "ssh root@{} \'exit\'".format(target))
    snmp_cmd = [ 'nc', target, '161', '</dev/null' ]
    hv_ver_bash_cmd = "ssh root@{} \"cat /onapp/onapp-store-install.version 2>/dev/null || cat /onapp/onapp-hv-tools.version 2>/dev/null || grep Version /onappstore/package-version.txt 2>/dev/null || echo '???'\""
    hv_ver_cmd = [ 'su', 'onapp', '-c', hv_ver_bash_cmd.format(target) ]
    hv_kernel_cmd = [ 'su', 'onapp', '-c', 'ssh root@{} "uname -r 2>/dev/null" 2>/dev/null'.format(target) ]
    hv_distro_cmd = [ 'su', 'onapp', '-c', 'ssh root@{} "cat /etc/redhat-release 2>/dev/null" 2>/dev/null'.format(target) ]
    #run all these, test them to make sure that they even work...
    rData['ping'] = runCmd(ping_cmd);
    rData['ssh'] = runCmd(ssh_cmd);
    rData['snmp'] = runCmd(snmp_cmd);
    rData['version'] = runCmd(hv_ver_cmd);
    rData['kernel'] = runCmd(hv_kernel_cmd);
    rData['distro'] = runCmd(hv_distro_cmd);
    return rData;

#
# def checkAllHVBS():
#     hvData = [ checkHVBSStatus(h['ip_address']) for h in HOST_INFO ];
#     return hvData;


def checkHVConn(from_ip, target='all'):
    if target == 'all':
        for h in HOST_INFO:
            
