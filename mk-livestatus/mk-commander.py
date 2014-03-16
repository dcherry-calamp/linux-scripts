#!/bin/env python2.6
#
# Description:
#   This utility provides an interface to a remote nagios server via the 
#   mk-livestatus API.
#
# Author: Devin Cherry <youshoulduseunix@gmail.com>
##
import socket, sys, time, os, pwd, atexit, commands, math
from optparse import OptionParser, OptionGroup
from datetime import timedelta
from signal import SIGTERM

verbose = False


class ServiceProblem:
    host = ''
    service = ''
    
    def __init__(self, h, s):
        self.host = h
        self.service = s


class NagiosServer:
    remote_targets = []
    address = ''
    port = 6557
    commands = { 
        'send_command':             'COMMAND',
        'get_timeperiods':          'GET timeperiods\n', 
        'get_contacts':             'GET contacts\n', 
        'get_contactgroups':        'GET contactgroups\n', 
        'get_columns':              'GET columns\n', 

        # don't modify the Columns, since they're referenced by index elsewhere
        'get_hosts':                'GET hosts\nColumns: host_name host_address\n', 
        'get_services':             'GET services\nColumns: host_name service_description service_state\n' +
                                    'Filter: in_notification_period = 1\n' +
                                    'Filter: notifications_enabled = 1\n', 
    
    ## These might be useful someday...
    #    'get_hostgroups':           'GET hostgroups\nOutputFormat: python\n', 
    #    'get_servicegroups':        'GET servicegroups\nOutputFormat: python\n', 
    #    'get_servicesbygroup':      'GET servicesbygroup\nOutputFormat: python\n', 
    #    'get_servicesbyhostgroup':  'GET servicesbyhostgroup\nOutputFormat: python\n', 
    #    'get_hostsbygroup':         'GET hostsbygroup\nOutputFormat: python\n', 
    #    'get_commands':             'GET commands\nOutputFormat: python\n', 
    #    'get_downtimes':            'GET downtimes\n', 
    #    'get_comments':             'GET comments\nOutputFormat: python\n', 
    #    'get_status':               'GET status\nOutputFormat: python\n', 
    #    'get_log':                  'GET log\nOutputFormat: python\n', 
    }

    def __init__(self, address='', port=6557):
        self.address = address
        self.port = port

    # Builds a proper livestatus+nagios command string. example:
    # "COMMAND [1376603554] ADD_HOST_COMMENT;server1.foo.com;1;MrTesty;RogerDodger\n"
    def buildCommand(self, optstring, date=time.time()):
        nag_cmd = self.commands['send_command'] + " [" + repr(date) + "] " + optstring.lstrip().rstrip() + "\n"
        return nag_cmd

    # sends a single mk-livestatus command
    def sendCommand(self, cmd):
        resp = ''
        retries = 0
    
        # retry for some types of exceptions
        while retries < 3:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(10)
            try:
                s.connect((self.address, self.port))
                if verbose: print "Sending Command: %s" % repr(cmd)
                s.sendall(cmd)
                s.shutdown(socket.SHUT_WR)
                
                buf = s.recv(4096)
                resp = buf
                while buf:
                    buf = s.recv(4096)
                    resp = resp + buf
                if verbose: print "OK"
                break
            except socket.timeout, e:
                sys.stderr.write("Unable to connect to [%s:%s]: %s\n" % (self.address, self.port, "Connection Timed Out."))
                sys.exit(1)
            except socket.error, e:
                sys.stderr.write("Unable to connect to [%s:%s]: %s\n" % (self.address, self.port, e.strerror))
                sys.exit(1)
            except IOError, e:
                if verbose: sys.stderr.write("IO Error: retrying...\n")
                time.sleep(3)
                retries = retries + 1
                continue
            except Exception, e:
                sys.stderr.write("UNKNOWN ERROR: %s\n" % type(e))
                sys.exit(1)
            finally:
                s.close()
        return resp

    def _fetchRemoteTargets(self):
        # if we don't have a dictionary of valid remote targets yet, build it.
        if len(self.remote_targets) < 1:
            hostData = self.sendCommand(self.commands['get_hosts']).split('\n')
            try:
                for line in hostData:
                    lineTokens = line.split(';')
                    self.remote_targets.append(lineTokens[0])
            except:
                pass

    # checks for existence of user-supplied target hostname on remote server
    def targetIsValid(self, host):
        if host == '': return False
        self._fetchRemoteTargets()

        # check the dictionary for the specified host
        if host in self.remote_targets:
            return True
        return False

    # print a listing of target servers on the remote nagios host
    def listValidTargets(self):
        self._fetchRemoteTargets()
        return sorted(self.remote_targets)

    # return a list of current service problems on the nagios host
    def getCurrentProblems(self):
        problems = []
        hostData = self.sendCommand(self.commands['get_services']).split('\n')
        for service in hostData:
            if service.lstrip().rstrip() != '':
                parts = service.split(';')
                if int(parts[2]) > 0:
                    problems = problems + [ServiceProblem(parts[0], parts[1])]
        return problems


class ReenablerDaemon:
    def __init__(self, bin_name, opts, pidfile):
        self.stdin = '/dev/null'
        #self.stdout = '/tmp/daemon.stdout.log'
        #self.stderr = '/tmp/daemon.stderr.log'
        self.stdout = '/dev/null'
        self.stderr = '/dev/null'
        self.initialTime = timedelta(seconds=time.time())
        self.pidfile = pidfile + "." + str(self.initialTime.days) + "-" + str(self.initialTime.seconds)
        self.job_str = "%s -H %s -p %d -e -t \"%s\"" % (bin_name, opts.address, opts.port, opts.target_servers)
        self.reenable_delta = timedelta(seconds=math.fabs(opts.reenable_after))

    def delpid(self):
        os.remove(self.pidfile)

    def daemonize(self):
        try:
            pid = os.fork()
            if pid > 0:
                # exit first parent
                sys.exit(0)
        except OSError, e:
            sys.stderr.write("ERROR: Failed initial fork!\n")
            sys.stderr.write("       errno=%d; strerror=%s\n" % (e.errno, e.strerror))
            sys.exit(1)

        os.chdir("/")
        os.setsid()
        os.umask(0)
        try:
            pid = os.fork()
            if pid > 0:
                # exit second parent
                sys.exit(0)
        except OSError, e:
            sys.stderr.write("ERROR: Failed second fork!\n")
            sys.stderr.write("       errno=%d; strerror=%s\n" % (e.errno, e.strerror))
            sys.exit(1)

        # redirect file descriptors
        sys.stdout.flush()
        sys.stderr.flush()
        si = file(self.stdin, 'r')
        so = file(self.stdout, 'a+')
        se = file(self.stderr, 'a+', 0)
        os.dup2(si.fileno(), sys.stdin.fileno())
        os.dup2(so.fileno(), sys.stdout.fileno())
        os.dup2(se.fileno(), sys.stderr.fileno())

        atexit.register(self.delpid)
        pid = str(os.getpid())
        file(self.pidfile, 'w+').write("%s\n" % pid)

    def start(self):
        # Check for a pidfile to see if the daemon already runs
        try:
            pf = file(self.pidfile,'r')
            pid = int(pf.read().strip())
            pf.close()
        except IOError:
            pid = None
       
        if pid:
            message = "pidfile %s already exist. Daemon already running?\n"
            sys.stderr.write(message % self.pidfile)
            sys.exit(1)
        
        # Start the daemon
        self.daemonize()
        self.run()
 
    def stop(self):
        # Get the pid from the pidfile
        try:
            pf = file(self.pidfile,'r')
            pid = int(pf.read().strip())
            pf.close()
            self.delpid()
        except IOError:
            pid = None
    
        if not pid:
            message = "pidfile %s does not exist. Daemon not running?\n"
            sys.stderr.write(message % self.pidfile)
            return # not an error in a restart
 
        # Try killing the daemon process       
        try:
            while True:
                os.kill(pid, SIGTERM)
                time.sleep(0.1)
        except OSError, err:
            err = str(err)
            if err.find("No such process") > 0:
                if os.path.exists(self.pidfile):
                    os.remove(self.pidfile)
            else:
                print str(err)
                sys.exit(1)
 
    def restart(self):
        self.stop()
        self.start()
 
    def run(self):

        while True:
            time.sleep(1)

            # check time difference, and re-enable alerts when time is right
            if (timedelta(seconds=time.time()) - self.initialTime) >= self.reenable_delta:
                status = 1
                while status != 0:
                    (status, output) = commands.getstatusoutput(self.job_str)
                self.stop()



##################################
#           BEGIN MAIN           #
##################################

parser = OptionParser(version="%prog 0.2c", 
description="""This program provides functions
to either collect info from--or send a Nagios-specific command string to--a remote Nagios server
via the mk-livestatus API.""", 
epilog="""Quick Commands and Livestatus/Nagios Commands cannot be used together.
When specifying an mk-livestatus 'get_' command (which fetches Nagios server info),
you do not need to supply any additional options or flags. When specifying an mk-livestatus command
which attempts to run a Nagios-specific command on the remote server, you must supply a properly
formatted Nagios command string, as defined in the Nagios external commands documentation.
(http://old.nagios.org/developerinfo/externalcommands/commandlist.php)"""
)
optGroup = OptionGroup(parser, "General Options", "Options which affect all operations.")
optGroup.add_option("-H", "--livestatus-host", type='string', dest='address', 
                    help="The mk-livestatus/Nagios server to send commands to.",
                    default='')
optGroup.add_option("-p", "--livestatus-port", type='int', dest='port', 
                    help="The mk-livestatus port to connect to. (optional; default=6557)", 
                    default=6557)
optGroup.add_option("-v", "--verbose", action='store_true', dest='verbose', default=False)
parser.add_option_group(optGroup)

optGroup = OptionGroup(parser, "Quick Commands")
optGroup.add_option("-a", "--ack-problem", action='store_true', dest='ack_problem',
                    help="(interactive) Acknowledge a current service problem.", default=False)
optGroup.add_option("-d", "--disable-all-notifications", action='store_true', dest='disable_all_notifications',
                    help='Disable all service/host notifications for the given host. If this option is specified, \
you must supply a -t/--targets value.', default=False)
optGroup.add_option("-e", "--enable-all-notifications", action='store_true', dest='enable_all_notifications',
                    help='Enable all service/host notifications for the given host. If this option is specified, \
you must supply a -t/--targets value.', default=False)
optGroup.add_option("-t", "--targets", type='string', dest='target_servers',
                    help="The servers who's service/host notifications should be (en/dis)abled.\
(single host, or comma-delimited list).", default='')
optGroup.add_option("-r", "--reenable-after", type='int', dest='reenable_after',
                    help="The time (in seconds) after which notifications will be automatically re-enabled. (optional)",
                    default=0)
optGroup.add_option("-L", "--list-remote-targets", action='store_true', dest='list_remote_targets',
                    help="Print a list of known targets on the remote Nagios/livestatus server and exit.",
                    default=False)
parser.add_option_group(optGroup)

optGroup = OptionGroup(parser, "Livestatus/Nagios Commands")
optGroup.add_option("-l", "--list-mk-commands", action='store_true', dest='list_mk_commands', 
                    help="List available mk-livestatus commands and exit.", default=False)
optGroup.add_option("-c", "--command", type='string', dest='command', 
                    help="The mk-livestatus command to send.", 
                    default='')
optGroup.add_option("-n", "--nagios-command-string", type='string', dest='nagios_cmd_string', 
                    help='The custom Nagios command string to send. (i.e. "<NAGIOS_CMD>;<NAGIOS_CMD_OPTIONS>;\
...")', default='')
parser.add_option_group(optGroup)

try:
    (options, args) = parser.parse_args()
except:
    sys.exit(1)

nagios = NagiosServer(address=options.address, port=options.port)
verbose = options.verbose

if options.list_mk_commands:
    print "Available mk-livestatus commands:"
    for cmd in sorted(nagios.commands.keys()):
        print '\t', cmd
    sys.exit(0)

if nagios.address == '':
    sys.stderr.write("ERROR: You must specify a --livestatus-host. (-h for help)\n")
    parser.print_usage()
    sys.exit(1)

if options.list_remote_targets:
    tmp = ''
    for target in nagios.listValidTargets():
        tmp = tmp + target + ', '
    print "Known targets on host %s:" % repr(options.address)
    print tmp
    sys.exit(0)

if options.ack_problem:
    problems = nagios.getCurrentProblems()
    problemNum = 1
    for p in problems:
        print "(" + str(problemNum) + ") " + p.host + ": " + p.service
        problemNum = problemNum + 1
    num = int(raw_input("Enter a problem number to ACK (0 to quit): "))
    if num == 0: sys.exit(0)
    tmp = "ACKNOWLEDGE_SVC_PROBLEM;" + problems[num-1].host + ";" + problems[num-1].service + ";2;1;1;" 
    tmp = tmp + pwd.getpwuid(os.getuid())[0] 
    tmp = tmp + ";" + raw_input("Enter a short comment: ")
    ret = nagios.sendCommand(nagios.buildCommand(tmp))
    if ret.lstrip().rstrip() != '':
        print ret
    sys.exit(0)

# process the quick commands, if supplied
if options.disable_all_notifications ^ options.enable_all_notifications:
    if options.command != '': 
        sys.stderr.write("ERROR: conflicting options specified! (-h for help)\n")
        sys.exit(1)
    if options.target_servers == '':
        sys.stderr.write("ERROR: you must specify --targets with this option. (-h for help)\n")
        sys.exit(1)

    targets = options.target_servers.rstrip().split(',')
    for target in targets:
        if not nagios.targetIsValid(target):
            sys.stderr.write("WARNING: skipping invalid target %s. Target doesn't exist on server %s. (-h for help)\n" \
                             % (repr(target), repr(options.address)))
            continue
    
        # we get the uid, then convert to a proper username because running this script from cron will 
        # cause os.getlogin() to fail
        if options.disable_all_notifications:
            tmpCmds = ["DISABLE_HOST_SVC_NOTIFICATIONS;%s\n" % target,
                       "DISABLE_HOST_NOTIFICATIONS;%s\n" % target,
                       "ADD_HOST_COMMENT;%s;1;%s;Host and service notifications disabled from command line.\n" \
                         % (target, pwd.getpwuid(os.getuid())[0])]
        elif options.enable_all_notifications:
            tmpCmds = ["ENABLE_HOST_SVC_NOTIFICATIONS;%s\n" % target,
                       "ENABLE_HOST_NOTIFICATIONS;%s\n" % target,
                       "ADD_HOST_COMMENT;%s;1;%s;Host and service notifications enabled from command line.\n" \
                         % (target, pwd.getpwuid(os.getuid())[0])]

        # finally, run the commands
        for c in tmpCmds:
            ret = nagios.sendCommand(nagios.buildCommand(c))
            if ret.lstrip().rstrip() != '':
                print ret

    # do this last, since it will exit this parent process upon daemonization
    if options.reenable_after > 0 and options.disable_all_notifications and __name__ == "__main__":
        reenabler = ReenablerDaemon(os.path.abspath(sys.argv[0]), options, '/tmp/.nagios_alert_reenabler.pid')
        reenabler.start()

    sys.exit(0)

# process a custom nagios command, if supplied
if options.nagios_cmd_string != '':
    print nagios.sendCommand(nagios.buildCommand(options.nagios_cmd_string))
    sys.exit(0)

# process an mk-livestatus command, if supplied
if options.command != '':
    if nagios.commands.has_key(options.command):
        if options.disable_all_notifications or options.enable_all_notifications: 
            sys.stderr.write("ERROR: conflicting options specified! (-h for help)\n")
            sys.exit(1)
        if options.command == 'send_command':
            if options.nagios_cmd_string != '':
                print nagios.sendCommand(nagios.buildCommand(options.nagios_cmd_string))
            else:
                sys.stderr.write("ERROR: you must supply a --nagios-command-string with this command! (-h for help)\n")
                sys.exit(1)
        else:
            print nagios.sendCommand(nagios.commands[options.command])
    
        sys.exit(0)
    else:
        sys.stderr.write("ERROR: invalid mk-livestatus command specified! (-h for help)\n")
        parser.print_usage()
        sys.exit(1)
else:
    sys.stderr.write("ERROR: Please specify an action. (-h for help)\n")
    parser.print_usage()
    sys.exit(1)


