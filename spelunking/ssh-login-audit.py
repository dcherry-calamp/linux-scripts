#!/bin/env python2.6
#
# Description:
# This utility does a simple system audit on the local host, printing 
# relevant information about system security. 
#
# Author: Devin Cherry <devincherry@gmail.com>
##
import re, os, sys, commands, tempfile

if os.geteuid() != 0:
    sys.stderr.write("ERROR: you must run this script as root!\n")
    sys.exit(1)

# holds details about a user on the system
class LocalUser:
    def __init__(self, username="", password="", home="", shell=""):
        self.name = username
        self.shell = shell
        self.home = home
        self.password = password
        self.ssh_private_keys = []      # TODO: enumerate these
        self.ssh_authorized_keys = []
        self.ssh_allowed_user = 0
        self.ssh_root_login_enabled = 0

    def canLogin(self):
        if self.password != "" and self.shell != "":
            if self.name == 'root':
                if self.ssh_allowed_user == 1 and self.ssh_root_login_enabled == 1:
                    return True
                else:
                    return False
            else:
                if self.ssh_allowed_user == 1:
                    return True
                else:
                    return False
        else:
            return False

# holds details about the system
class LocalSystem:
    def __init__(self, hostname='localhost'):
        self.hostname = hostname
        self.sshd_enabled = False
        self.ssh_pubkey_login_allowed = True

    def remoteLoginEnabled(self):
        if self.sshd_enabled == True and self.ssh_pubkey_login_allowed == True:
            return True
        else:
            return False


# looks for users with valid shells/passwords, checks for SSH login ability, 
# and populates the database info for the users.
def getUserData(usersList):
    f = open("/etc/passwd", 'r')
    fs = open("/etc/shadow", 'r')
    nonShells = re.compile(r'^[\S\/]+(false|nologin|sync)$')
    nonPasswords = re.compile(r'^[\!\*]+.*')
    
    # get users with valid shells
    passwdData = f.readlines()
    for line in passwdData: 
        splitData = line.split(":")

        usersList[splitData[0]] = LocalUser(splitData[0], "", splitData[5], "")

        m = nonShells.match(splitData[6])
        if not m:
            usersList[splitData[0]].shell = splitData[6].strip()
    
    # get users with valid passwords
    shadowData = fs.readlines()
    for line in shadowData: 
        splitData = line.split(":")
        m = nonPasswords.match(splitData[1])
        if not m:
            if usersList.has_key(splitData[0]):
                usersList[splitData[0]].password = splitData[1]
    f.close()
    fs.close()
    

# parses specific values from sshd_config, to see if users can login
def getSshdConfig(usersList, localSystem):
    configLinesRegex = {}
    configLinesRegex['AllowUsers'] = re.compile(r'^AllowUsers\s(?P<users>.*)$')
    configLinesRegex['PermitRootLogin'] = re.compile(r'^PermitRootLogin\s(?P<root>.*)$')
    configLinesRegex['PubkeyAuthentication'] = re.compile(r'^PubkeyAuthentication\s(?P<pubkey>.*)$')

    try:
        fSsh = open("/etc/ssh/sshd_config", 'r')

        # TODO: need to actually check that the service is running for this to be valid
        localSystem.sshd_enabled = True
    except:
        sys.stderr.write("WARNING: file [/etc/ssh/sshd_config] doesn't exist or could not be opened!\n")
        localSystem.sshd_enabled = False
        return 1

    # get SSH config lines
    sshdData = fSsh.readlines()
    for line in sshdData:
        for regexName in sorted(configLinesRegex.keys()):
            m = configLinesRegex[regexName].match(line)

            # if user is one of the AllowUsers
            if m and regexName == 'AllowUsers':
                tmpUsers = m.group('users').split()
                for user in tmpUsers:
                    try:
                        # handle 'user@host' form
                        (u, h) = user.split("@")
                        if usersList.has_key(u):
                            usersList[u].ssh_allowed_user = 1
                    except:
                        if usersList.has_key(user):
                            usersList[user].ssh_allowed_user = 1

            # no AllowUsers line found in config, so all are allowed
            elif not m and regexName == 'AllowUsers':
                for u in usersList:
                    usersList[u].ssh_allowed_user = 1

            # if root login permitted, and user is root
            elif m and regexName == 'PermitRootLogin':
                if usersList.has_key('root'):
                    if m.group('root').lower().strip() == 'no' or m.group('root').lower().strip() == 'false':
                        usersList['root'].ssh_root_login_enabled = 0
                    elif m.group('root').lower().strip() == 'yes' or m.group('root').lower().strip() == 'true':
                        usersList['root'].ssh_root_login_enabled = 1
            
            # if SSH public key auth is permitted
            elif m and regexName == 'PubkeyAuthentication':
                if m.group('pubkey').lower().strip() == 'no' or m.group('pubkey').lower().strip() == 'false':
                    localSystem.ssh_pubkey_login_allowed = False
                elif m.group('pubkey').lower().strip() == 'yes' or m.group('pubkey').lower().strip() == 'true':
                    localSystem.ssh_pubkey_login_allowed = True
    
    fSsh.close()


# looks for users' SSH keys, and checks authorized_keys entries
# TODO: handle AuthorizedKeysFile line in config
def getSshAuthorizedKeys(usersList):
    authKeysPaths = []    
    commentReg = re.compile("^[\S]{0,}#+")

    for user in usersList.keys():
        if usersList[user].canLogin():
            authKeysPaths.append(usersList[user].home + "/.ssh/authorized_keys")
            authKeysPaths.append(usersList[user].home + "/.ssh/authorized_keys2")
            for path in authKeysPaths:
                try:
                    f = open(path, 'r')
        
                    keys = f.readlines(512)
                    for key in keys:
                        # ignore comment lines
                        match = commentReg.match(key)
                        if match:
                            continue
                        tmpFile = tempfile.NamedTemporaryFile()
                        tmpFile.write(key)
                        tmpFile.flush()
                        tmpCommand = "ssh-keygen -l -f %s" % tmpFile.name
                        (status, fingerprint) = commands.getstatusoutput(tmpCommand)
                        usersList[user].ssh_authorized_keys.append(fingerprint)
                        tmpFile.close()
        
                    f.close()
                except IOError:
                    pass
            authKeysPaths = []


# looks for services with a daemon socket
def getListeningServices():
    pass



#########################
###  BEGIN EXECUTION  ###
#########################

# holds all the info about discovered users
usersList = {}
localSystem = LocalSystem('localhost')

getUserData(usersList)
getSshdConfig(usersList, localSystem)
getSshAuthorizedKeys(usersList)

# print users who can login
print "Valid Accounts with SSH Privileges:"
for user in sorted(usersList.keys()):
    if usersList[user].canLogin():
        print "\t" + usersList[user].name 
print ""

# print keys for users
if localSystem.remoteLoginEnabled():
    print "This system has SSH pubkey authentication enabled. Searching for keys..."
    for user in sorted(usersList.keys()):
        if usersList[user].canLogin():
            print "Checking SSH authorized_keys for user [%s]..." % user
            for key in usersList[user].ssh_authorized_keys:
                print "\t" + key
    print ""
else:
    print "This system has SSH pubkey authentication disabled.\n" 


