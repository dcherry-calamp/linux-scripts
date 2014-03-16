#!/usr/bin/env python2.6
#
# Description:
#   This program wraps the ec2run command, and uses the arguments to that command
#   for further company/environment-specific configuration & deployment automation. 
#   Added functionality includes:
#       - Puppet certificate signing
#       - Puppet node manifest generation
#       - DNS record auto-population
#       - user-data instance configuration
#
# Caveats:
#   Sudo commands will fail if they require a password, since no tty present...
#   Ensure the puppet server has a sudo config that allows NOPASSWD for these commands:
#
# Author: Devin Cherry <youshoulduseunix@gmail.com>
#################################################################
import paramiko, sys, time, commands, re
from string import join
from optparse import OptionParser, OptionGroup

verbose = False
debug = False
templates_dir = '/etc/puppet/common/templates'
nodes_dir = '/etc/puppet/common/nodes.d'
nodes_pp = '/etc/puppet/common/nodes.pp'
ec2run_opts = {
  'aws_access_key':     ('',''),
  'aws_secret_key':     ('',''),
  'security_token':     ('',''),
  'private_key':        ('',''),
  'cert':               ('',''),
  'url':                ('',''),
  'region':             ('',''),
  'show_headers':       ('',''),
  'debug':              ('',''),
  'show_empty_fields':  ('',''),
  'hide_tags':          ('',''),
  'connection_timeout': ('',''),
  'request_timeout':    ('',''),
  'block_device_mapping': ('',[]),   # can be specified multiple times
  'user_data':          ('',''),
  'user_data_file':     ('',''),
  'security_groups':    ('',''),
  'key':                ('',''),
  'monitor':            ('',''),
  'instance_count':     ('','1'),
  'subnet':             ('',''),
  'instance_type':      ('',''),
  'availability_zone':  ('',''),
  'addressing':         ('',''),
  'disable_api_termination': ('',''),
  'instance_initiated_shutdown_behavior': ('',''),
  'kernel':             ('',''),
  'license_pool':       ('',''),
  'ramdisk':            ('',''),
  'placement_group':    ('',''),
  'private_ip_address': ('',''),
  'iam_profile':        ('',''),
  'client_token':       ('',''),
  'tenancy':            ('',''),
  'ebs_optimized':      ('',''),
  'network_attachment': ('',''),
  'secondary_private_ip_address': ('',''),
  'secondary_private_ip_address_count': ('',''),
}


# Ec2Instance: A class for functions/variables specific to EC2 instances
class Ec2Instance:
    ip_address = ''
    dns_name = ''
    instance_id = ''
    subnet_id = ''
    availability_zone = ''
    ami_id = ''
    hostclass = ''

    def __init__(self, instance_id=''):
        self.instance_id = instance_id
## End Class <Ec2Instance>


# PuppetMaster: A class for functions which are to be executed on a Puppet master server.
class PuppetMaster:
    client = None
    is_connected = False
    connect_address = ''
    puppet_client_timeout = 0

    def __init__(self, address='', clientTimeout=900):
        self.connect_address = address
        self.puppet_client_timeout = clientTimeout


    # establish SSH connection to puppetmaster
    def connect(self):
        if not self.is_connected:
            if verbose: print "Connecting to server %s" % self.connect_address
            self.client = paramiko.SSHClient()
            self.client.load_system_host_keys() 
            self.client.set_missing_host_key_policy(paramiko.RejectPolicy()) 
            try:
                self.client.connect(self.connect_address) 
                if verbose: print "SSH Connection to <%s> Established!" % self.connect_address
                self.is_connected = True
            except:
                self.is_connected = False
                self.errorExit("ERROR: connect to puppetmaster <%s>!\n" % self.connect_address)
        else:
            sys.stderr.write("WARNING: connection to puppetmaster <%s> already established.\n" % self.connect_address)


    # close the SSH connection to puppetmaster
    def disconnect(self):
        if self.is_connected:
            try:
                self.client.close()
            except:
                sys.stderr.write("WARNING: failed to properly close connection to puppetmaster <%s>.\n" % self.connect_address)
            finally:
                self.is_connected = False
        else:
            sys.stderr.write("WARNING: attempt to close non-existent SSH connection.\n")


    # Gets a list of SSL certs waiting to be signed on the puppet-master
    def signPuppetSslRequest(self, instanceName):
        keepTrying = True
        if not self.is_connected:
            self.connect()

         # start a timer for waiting for the client cert to appear on the puppetmaster
        self.startTime = time.time()
      
        # keep looking for the client cert request until timeout is reached
        if verbose: print "<%s> -- Searching for puppet client certificate request [%s]..." % (self.connect_address, instanceName),
        while keepTrying:

            # grab the list of certs to sign
            stdin, stdout, stderr = self.client.exec_command('sudo /usr/bin/puppet cert list')
            if verbose:
                for line in stderr.readlines():
                    if len(line.lstrip().rstrip()) > 0:
                        sys.stderr.write("\n<%s> -- %s\n" % (self.connect_address, line))

            output = stdout.readlines()
            if debug:
                for line in output:
                    if len(line.lstrip().rstrip()) > 0:
                        sys.stderr.write("\n<%s> -- %s\n" % (self.connect_address, line))
        
            # if there are cert reqs waiting; 
            # search the list for instanceName;
            # if there's a match, sign the certificate & logout.
            if len(output) > 0:
                certReqSigned = False
                quotedInstanceName = '"' + instanceName + '"'

                for req in output:
                    tmpName = req.lstrip().split()[0]
                    tmpFingerprint = req.lstrip().split()[1]
                    if tmpName == quotedInstanceName:
                        if verbose: print "\n<%s> -- Signing Cert Request: %s %s\n" % \
                                          ( self.connect_address, tmpName, tmpFingerprint ),
    
                        stdin, stdout, stderr = self.client.exec_command('sudo /usr/bin/puppet cert sign ' + tmpName)
                        if debug:
                            print "<%s> -- %s" % (self.connect_address, stdout.readlines())
                        if verbose:
                            print "<%s> -- %s" % (self.connect_address, stderr.readlines())

                        certReqSigned = True
                        break
    
                if certReqSigned:
                    break
                else:
                    ret = self.checkTime() 
                    if ret == 0:
                        continue
                    else:
                        keepTrying = False

            # no output recv'd, check timeout and keep waiting
            else:
                ret = self.checkTime() 
                if ret == 0:
                    continue
                else:
                    keepTrying = False


    # checks elapsed time while waiting for new server to request a certificate from puppetmaster
    def checkTime(self):
        if verbose: 
            sys.stdout.write(" .")
            sys.stdout.flush()

        elapsedTime = (time.time() - self.startTime)
        if elapsedTime < self.puppet_client_timeout:
            time.sleep(10)
            return 0
        else:
            sys.stderr.write("\n<%s> -- WARNING: did not receive a certificate request from client.\n" % self.connect_address)
            return -1


    # lists the available hostclass templates on the remote puppetmaster server
    def getAvailableHostclasses(self):
        if not self.is_connected:
            self.connect()

        # This assumes hostclass templates are named "<hostclass>.template".
        cmd = "for template in $(ls " + templates_dir + "); do echo $template | cut -f1 -d.; done"
        stdin, stdout, stderr = self.client.exec_command(cmd)
        if len(stderr.readlines()) > 0:
            return join(stderr.readlines())
        return (' ' + join(stdout.readlines()))


    # create a node manifest for the new instance, using pre-defined templates
    def provisionNodeManifest(self, instanceDnsName, hostclass):
        if not self.is_connected:
            self.connect()

        # First, ensure the selected hostclass is available on the puppetmaster
        hc_pattern = r'^\s(' + hostclass + ')$'
        reObj = re.compile(hc_pattern, re.MULTILINE)
        hostclasses = self.getAvailableHostclasses()
        try:
            # get the hostclass from the cmd output
            hc_match = reObj.findall(hostclasses)
        except IndexError:
            self.errorExit("<%s> -- ERROR: hostclass <%s> not found!\n" \
                           % (self.connect_address, hostclass))
        
        # Then, ensure the manifests doesn't already exist (don't want to overwrite it!)
        cmd = "ls " + nodes_dir + "/" + instanceDnsName + ".pp"
        stdin, stdout, stderr = self.client.exec_command(cmd)
        output = join(stdout.readlines())
        if len(output) > 0:
            m = re.search(nodes_dir + "/" + instanceDnsName + ".pp$", output)
            if m != None:
                sys.stderr.write("<%s> -- WARNING: manifest already exists for host <%s>! NOT overwriting.\n"
                                 % (self.connect_address, instanceDnsName))
                return

        # Now, copy the manifest template (safely)
        cmd = "cp -b " + templates_dir + "/" + hostclass + ".template " \
              + nodes_dir + "/" + instanceDnsName + ".pp"
        stdin, stdout, stderr = self.client.exec_command(cmd)
        if len(stderr.readlines()) > 0:
            sys.stderr.write("<%s> -- WARNING: there was a problem creating the manifest:\n---\n%s\n---\n" 
                             % (self.connect_address, join(stderr.readlines())))
            return
        if verbose: print ' ' + join(stdout.readlines())

        # Finally, substitute the placeholder text in the template with our instance DNS name,
        # and touch the main nodes.pp file so puppetd knows about the new manifest.
        cmds = []
        cmds.append(("sed -i 's/__AWS_NODENAME/" + instanceDnsName + "/' " + nodes_dir + "/" \
                     + instanceDnsName + ".pp"))
        cmds.append(("touch " + nodes_pp))
        for cmd in cmds:
            stdin, stdout, stderr = self.client.exec_command(cmd)
            if len(stderr.readlines()) > 0:
                sys.stderr.write("<%s> -- WARNING: there was a problem creating the manifest:\n---\n%s\n---\n" 
                                 % (self.connect_address, join(stderr.readlines())))
                return

        if verbose:
            print "<%s> -- Created node manifest [%s/%s.pp]." % (self.connect_address, nodes_dir, instanceDnsName)

    # create a DNS A record for this instance
    def addDnsRecord(self, dnsName, ipAddr, dnsDataFile):
        dns_A_pattern = re.compile(r'^=[a-zA-Z0-9.-]+:(\d{1,3}.\d{1,3}.\d{1,3}.\d{1,3})', re.MULTILINE)
        dns_CNAME_pattern = re.compile(r'^C([a-zA-Z0-9.-]+):.*', re.MULTILINE)
        if not self.is_connected:
            self.connect()

        try:
            sftp_client = self.client.open_sftp()

            # FIXME: This is kinda dangerous, since we never acquire a remote file lock...
            dnsFile = sftp_client.open(dnsDataFile, mode='a+')
            dnsFile.prefetch()
            dnsData = dnsFile.readlines()

            # If an A record exists with same IP, or if a CNAME which would match the hostname part of
            # the A record already exists, skip DNS provisioning. 
            # Else, create a new A record.
            a_records = []
            cname_records = []
            for line in dnsData:
                a_records = a_records + dns_A_pattern.findall(line.rstrip())
            if ipAddr in a_records:
                print "<%s> -- DNS A-record already exists for %s. Skipping..." % (self.connect_address, ipAddr)
                return 1
            if dnsName in cname_records:
                print "<%s> -- DNS CNAME-record for %s already exists! Skipping..." % (self.connect_address, dnsName)
                return 1

            newRecord = "\n# autogenerated entry follows.\n"
            newRecord = newRecord + "=" + dnsName + ":" + ipAddr + "\n"
            dnsFile.write(newRecord)
            dnsFile.flush()
            print "\n<%s> -- DNS File Modified: %s" % (self.connect_address, dnsDataFile)
            print "<%s> -- Provisioned new DNS A-record: \"=%s:%s\"" % (self.connect_address, dnsName, ipAddr)
        except IOError, e:
            sys.stderr.write("<%s> -- ERROR: IOError on file [%s]!\n" % (self.connect_address, dnsDataFile))
            sys.stderr.write("<%s> -- error=\"%s\", errno=%s\n" % (self.connect_address, e, e.errno))
        except Exception, e:
            sys.stderr.write("<%s> -- ERROR: Failed to provision DNS record! %s\n" % (self.connect_address, e))
        finally:
            dnsFile.close()
        return 0

    # print an error message and exit
    def errorExit(self, msg):
        sys.stderr.write(msg)
        self.disconnect()
        sys.exit(1)
## END CLASS <PuppetMaster>


# make sure we're using at least Python 2.6
def checkEnv():
    if sys.hexversion < 0x02060000:
        sys.stderr.write("\n\tERROR: Your Python version is too old! Upgrade to 2.6+ please.\n\n")
        sys.exit(1)

# print ec2-run-instances help
def ec2_help_callback(option, opt, value, parser):
    setattr(parser.values, option.dest, True)
    tmpCmd = "ec2-run-instances -h"
    (status, output) = commands.getstatusoutput(tmpCmd)
    print output

# build the instance FQDN from ec2run options
def getInstance(options, ec2runOutput):
    id_pattern = re.compile(r'^INSTANCE\s+(i-[a-f0-9]{8})', re.MULTILINE)
    ip_pattern = re.compile(r'^PRIVATEIPADDRESS\s+(\d{1,3}.\d{1,3}.\d{1,3}.\d{1,3})', re.MULTILINE)
    subnet_pattern = re.compile(r'\s(subnet\-[a-zA-Z0-9]+)', re.MULTILINE)
    instance = Ec2Instance()
    instance.hostclass = options.hostclass

    # first get instance_id
    try:
        instance.instance_id = id_pattern.findall(ec2runOutput)[0].rstrip().lstrip()
    except IndexError:
        sys.stderr.write("ERROR: ec2run failed to provide an instance ID! ec2run output follows:\n")
        sys.stderr.write("---\n%s\n---\n" % ec2runOutput)
        sys.exit(1)

    # Now get ip_address & subnet_id. ec2run doesn't always give this info in the output, so
    # we have to look for it explicitly, for up to 60 seconds.
    startTime = time.time()
    timeDiff = 0
    while timeDiff < 60:
        try:
            cmd = "ec2-describe-network-interfaces --filter \"attachment.instance-id=" + instance.instance_id + "\""
            (cmd_status, output) = commands.getstatusoutput(cmd)
            if cmd_status == 0:
                instance.ip_address = ip_pattern.findall(output, re.MULTILINE)[0].rstrip().lstrip()
                instance.subnet_id = subnet_pattern.findall(output, re.MULTILINE)[0].rstrip().lstrip()

                # got our ip & subnet, so let's bail
                break
            else:
                sys.stderr.write("ERROR: ec2-describe-network-interfaces exited with status %s. Output follows:" % status)
                sys.stderr.write("\n---\n%s\n---\n" % output)
                sys.exit(1)
        except IndexError:
            if options.debug:
                sys.stderr.write("WARNING: ec2run output failed to provide IP_ADDRESS and/or SUBNET_ID. Output follows.")
                sys.stderr.write("\n---\n" + ec2runOutput + "\n---\n")
            if options.verbose:
                print "NOTICE: could not get IP address and subnet. Retrying..."
        time.sleep(5)
        timeDiff = time.time() - startTime

    # get az from subnet description
    tmpCmd = "ec2-describe-subnets " + instance.subnet_id
    (status, output) = commands.getstatusoutput(tmpCmd)
    try:
        if status == 0:
            instance.availability_zone = output.split()[6]   
    except IndexError:
        sys.stderr.write("ERROR: ec2-describe-subnets exited with status %s. Output follows:" % status)
        sys.stderr.write("\n---\n" + output + "\n---\n")
        sys.exit(1)

    # build proper DNS name from instance properties (i.e. foo-10-0-0-254.us-east-1a.foo.bar)
    ip_dashed = instance.ip_address.replace(".", "-")
    instance.dns_name = instance.hostclass + "-" + ip_dashed + "." + instance.availability_zone + ".foo.bar"

    return instance


# store an ec2run string option
def ec2opt_callback(option, opt, value, parser):

    # handle options that can be specified multiple times
    if option.dest == 'block_device_mapping':
        if len(ec2run_opts[option.dest][1]) > 0:
            ec2run_opts[option.dest][1].append("'" + value + "'")
        else:
            ec2run_opts[option.dest] = (opt, [("'" + value + "'")])

    # handle most standard options
    elif option.type == ('string' or 'int'):
        ec2run_opts[option.dest] = (opt, value)

    # leaves option's value empty for booleans
    else:   
        ec2run_opts[option.dest] = (opt, '')


# run ec2run command with specified options
def execute_ec2run(instance):
    ec2run_cmd = "ec2run"

    if len(ec2run_opts['debug'][0]) > 1:
        print "ec2run options specified:"
        for key in ec2run_opts.keys():
            if ec2run_opts[key][0] != '':
                print "\t%s=%s" % (ec2run_opts[key][0], ec2run_opts[key][1])

    for key in ec2run_opts.keys():
        if ec2run_opts[key][0] != "":
            # handle args that can be specified multiple times
            if ec2run_opts[key][0] == '-b' or ec2run_opts[key][0] == '--block-device-mapping':
                for devMapping in ec2run_opts[key][1]:
                    ec2run_cmd = "%s %s %s " % (ec2run_cmd, ec2run_opts[key][0], devMapping)
            else:
                ec2run_cmd = "%s %s %s " % (ec2run_cmd, ec2run_opts[key][0], ec2run_opts[key][1])
    ec2run_cmd = ec2run_cmd + instance.ami_id

    # finally, execute the ec2run command-line
    print "Executing: %s" % ec2run_cmd
    (status, output) = commands.getstatusoutput(ec2run_cmd)
    if status != 0:
        sys.stderr.write("ERROR: ec2run exited with status %s. Output follows.\n---\n" % status)
        sys.stderr.write(output + "\n---\n")
        sys.exit(1)

    return output



###################################
#           BEGIN MAIN            #
###################################
instance = Ec2Instance()

# make sure the user's system can use this tool
checkEnv()


# handle CLI options
parser = OptionParser(version='%prog 0.2d', 
                      description='This utility wraps Amazon\'s ec2run command, providing' 
                      + ' additional functions to handle Puppet provisioning, DNS entries,'
                      + ' and instance user-data configuration.')
parser.add_option('-?', '--ec2run-help', action='callback', callback=ec2_help_callback,
                  help='Print ec2run options help.', dest='exit')
optGroup = OptionGroup(parser, "ec2run Options", "These directly translate to ec2run options.")
optGroup.add_option('-O', '--aws-access-key', type='string', action='callback', 
                    callback=ec2opt_callback, dest='aws_access_key')
optGroup.add_option('-W', '--aws-secret-key', type='string', action='callback', 
                    callback=ec2opt_callback, dest='aws_secret_key')
optGroup.add_option('-T', '--security-token', type='string', action='callback', 
                    callback=ec2opt_callback, dest='security_token')
optGroup.add_option('-K', '--private-key', type='string', action='callback', 
                    callback=ec2opt_callback, dest='private_key')
optGroup.add_option('-C', '--cert', type='string', action='callback', 
                    callback=ec2opt_callback, dest='cert')
optGroup.add_option('-U', '--url', type='string', action='callback', 
                    callback=ec2opt_callback, dest='url')
optGroup.add_option('--region', type='string', action='callback', 
                    callback=ec2opt_callback, dest='region')
optGroup.add_option('-H', '--headers', action='callback', 
                    callback=ec2opt_callback, dest='show_headers')
optGroup.add_option('--debug', action='callback', dest='debug', 
                    callback=ec2opt_callback)
optGroup.add_option('--show-empty-fields', action='callback', 
                    callback=ec2opt_callback, dest='show_empty_fields')
optGroup.add_option('--hide-tags', action='callback', 
                    callback=ec2opt_callback, dest='hide_tags')
optGroup.add_option('--connection-timeout', type='string', action='callback', 
                    callback=ec2opt_callback, dest='connection_timeout')
optGroup.add_option('--request-timeout', type='string', action='callback', 
                    callback=ec2opt_callback, dest='request_timeout')
optGroup.add_option('-b', '--block-device-mapping', type='string', action='callback', 
                    callback=ec2opt_callback, dest='block_device_mapping')
optGroup.add_option('-d', '--user-data', type='string', action='callback', 
                    callback=ec2opt_callback, dest='user_data')
optGroup.add_option('-f', '--user-data-file', type='string', action='callback', 
                    callback=ec2opt_callback, dest='user_data_file')
optGroup.add_option('-g', '--group', type='string', action='callback', 
                    callback=ec2opt_callback, dest='security_groups')
optGroup.add_option('-k', '--key', type='string', action='callback', 
                    callback=ec2opt_callback, dest='key')
optGroup.add_option('-m', '--monitor', action='callback', 
                    callback=ec2opt_callback, dest='monitor')
optGroup.add_option('-n', '--instance-count', type='string', action='callback', 
                    callback=ec2opt_callback, dest='instance_count')
optGroup.add_option('-s', '--subnet', type='string', action='callback', 
                    callback=ec2opt_callback, dest='subnet')
optGroup.add_option('-t', '--instance-type', type='string', action='callback', 
                    callback=ec2opt_callback, dest='instance_type')
optGroup.add_option('-z', '--availability-zone', type='string', action='callback', 
                    callback=ec2opt_callback, dest='availability_zone')
optGroup.add_option('--addressing', type='string', action='callback', 
                    callback=ec2opt_callback, dest='addressing')
optGroup.add_option('--disable-api-termination', action='callback', 
                    callback=ec2opt_callback, dest='disable_api_termination')
optGroup.add_option('--instance-initiated-shutdown-behavior', type='string', action='callback', 
                    callback=ec2opt_callback, dest='instance_initiated_shutdown_behavior')
optGroup.add_option('--kernel', type='string', action='callback', 
                    callback=ec2opt_callback, dest='kernel')
optGroup.add_option('--license-pool', type='string', action='callback', 
                    callback=ec2opt_callback, dest='license_pool')
optGroup.add_option('--ramdisk', type='string', action='callback', 
                    callback=ec2opt_callback, dest='ramdisk')
optGroup.add_option('--placement-group', type='string', action='callback', 
                    callback=ec2opt_callback, dest='placement_group')
optGroup.add_option('--private-ip-address', type='string', action='callback', 
                    callback=ec2opt_callback, dest='private_ip_address')
optGroup.add_option('-p', '--iam-profile', type='string', action='callback', 
                    callback=ec2opt_callback, dest='iam_profile')
optGroup.add_option('--client-token', type='string', action='callback', 
                    callback=ec2opt_callback, dest='client_token')
optGroup.add_option('--tenancy', type='string', action='callback', 
                    callback=ec2opt_callback, dest='tenancy')
optGroup.add_option('--ebs-optimized', action='callback', 
                    callback=ec2opt_callback, dest='ebs_optimized')
optGroup.add_option('-a', '--network-attachment', type='string', action='callback', 
                    callback=ec2opt_callback, dest='network_attachment')
optGroup.add_option('--secondary-private-ip-address', type='string', action='callback', 
                    callback=ec2opt_callback, dest='secondary_private_ip_address')
optGroup.add_option('--secondary-private-ip-address-count', type='string', action='callback', 
                    callback=ec2opt_callback, dest='secondary_private_ip_address_count')
parser.add_option_group(optGroup)

optGroup = OptionGroup(parser, "Custom Options", "Options specific to our infrastructure.")
optGroup.add_option('-v', '--verbose', action='store_true', dest='verbose', default=False)
optGroup.add_option('--puppetmaster', type='string', dest='puppetmaster', 
                    help='The puppet master server to connect to.', default='')
optGroup.add_option('--puppet-client-timeout', type='int', dest='puppet_client_timeout', 
                    help='Max time to wait (in seconds) for the puppetmaster to receive a certificate'
                         + ' request from the client. (default 15-min)', default=900)
optGroup.add_option('--hostclass', type='string', dest='hostclass',
                    help='The custom-defined hostclass.')
optGroup.add_option('--list-available-hostclasses', action='store_true', dest='list_available_hostclasses', 
                    help='Prints a list of available hostclasses on the specified puppetmaster.', 
                    default=False)
optGroup.add_option('--skip-puppet-provisioning', action='store_true', dest='skip_puppet_provisioning',
                    help='Do not create a new node manifest on the puppetmaster.', default=False)
optGroup.add_option('--djbdns-data-file', type='string', dest='djbdns_datafile', 
                    default='/etc/puppet/modules/ndjbdns/files/data',
                    help='The path to the DJBDNS data file on the puppetmaster.')
optGroup.add_option('--skip-dns-provisioning', action='store_true', dest='skip_dns_provisioning', 
                    help='Do not perform DNS provisioning on the puppetmaster.', default=False)
parser.add_option_group(optGroup)
parser.disable_interspersed_args()
try:
    (options, args) = parser.parse_args()
    if options.list_available_hostclasses:
        if options.puppetmaster != '':
            print "Available --hostclass Options on Puppetmaster <%s>:" % options.puppetmaster
            puppetMaster = PuppetMaster(address=options.puppetmaster)
            puppetMaster.connect()
            print puppetMaster.getAvailableHostclasses() 
            puppetMaster.disconnect()
            sys.exit(0)
        else:
            sys.stderr.write("ERROR: you must supply a --puppetmaster to check hostclasses on!\n")
            sys.exit(0)
    if options.hostclass == None:
        sys.stderr.write("ERROR: you must supply a --hostclass.\n")
        sys.exit(1)
    if options.exit:
        sys.exit(1)
    verbose = options.verbose
    debug = options.debug
except Exception as e:
    sys.stderr.write(str(e) + "\n")
    sys.exit(1)

# get the AMI id, which should be the only remaining positional argument
if len(args) < 1:
    sys.stderr.write("ERROR: you must specify an AMI ID as your final argument.\n")
    sys.exit(1)
else:
    instance.ami_id = args[0]

# TODO: Handle user-data configuration?
#       This would likely be a module which pulls from a database of build-specific facts (puppetdb?),
#       and based on input to this utility, we could dynamically generate a userdata script.
#       Optionally, we can build AMIs up to the point that they wouldn't need this script...

ec2runOutput = execute_ec2run(instance)
if options.verbose: print "ec2run output:\n---\n" + ec2runOutput + "\n---\n"

# Create a DNS name for the instance based on parsed instance attributes.
# (also, handle common issue where ec2run doesn't provide an IP in output...)
instance = getInstance(options, ec2runOutput)
print "Created EC2 Instance: %s, %s, %s" % (instance.instance_id, instance.dns_name, instance.ip_address)

# run the puppetmaster tasks, if user asked for it.
if options.puppetmaster != '':
    puppetMaster = PuppetMaster(address=options.puppetmaster, clientTimeout=options.puppet_client_timeout)
    puppetMaster.connect()
    if not options.skip_puppet_provisioning:
        print "<%s> -- Executing Puppet provisioning tasks..." % options.puppetmaster
        puppetMaster.provisionNodeManifest(instance.dns_name, instance.hostclass)
        puppetMaster.signPuppetSslRequest(instance.dns_name)

    if not options.skip_dns_provisioning:
        print "<%s> -- Executing DNS provisioning tasks..." % options.puppetmaster
        puppetMaster.addDnsRecord(instance.dns_name, instance.ip_address, options.djbdns_datafile)
    puppetMaster.disconnect()
else:
    print "--puppetmaster not specified; skipping Puppet & DNS provisioning..."

if options.verbose: print "Completed provisioning for instance: %s" % instance.dns_name

# TODO: Add SSH_KNOWN_HOSTS & clusterit.conf management?
#       SSH host keys are available as facter variables, so maybe puppet should handle this?
#       As it turns out, by using puppetdb, we can use "exported resources" to distribute keys within puppet.

