#!/bin/env python2.6
#
# Description:
# This utility does a simple system audit on the local host, printing 
# relevant information about system security. 
#
# Author: Devin Cherry <devincherry@gmail.com>
##
import re, os, sys, commands, tempfile


# flags for capabilities logic
SSH_ROOT_LOGIN_ENABLED = 1
SSH_PUBKEY_ENABLED = 2
SSH_EMPTY_PASSWD_ENABLED = 4
SSH_ALLOWED_USER = 8
USER_SHELL_VALID = 16
USER_PASSWD_VALID = 32
USER_PASSWD_BLANK = 64
USER_SSH_PUBKEY_EXISTS = 128


if sys.version_info < (2, 6): 
    sys.stderr.write("ERROR: this script requires python 2.6+!\n")
    sys.exit(1)

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
        self.ssh_authorized_keys = []
        self.login_flags = 0x0000

    def canLogin(self):
        # special case for root login; test this first
        if self.name == 'root':
            if ((self.login_flags & (SSH_ROOT_LOGIN_ENABLED | SSH_ALLOWED_USER | USER_PASSWD_VALID | USER_SHELL_VALID)) 
                                 == (SSH_ROOT_LOGIN_ENABLED | SSH_ALLOWED_USER | USER_PASSWD_VALID | USER_SHELL_VALID)): return True
            else: return False

        if ((self.login_flags & (SSH_ALLOWED_USER | USER_PASSWD_VALID | USER_SHELL_VALID)) 
                             == (SSH_ALLOWED_USER | USER_PASSWD_VALID | USER_SHELL_VALID)): return True

        if ((self.login_flags & (SSH_ALLOWED_USER | SSH_EMPTY_PASSWD_ENABLED | USER_SHELL_VALID | USER_PASSWD_BLANK))
                             == (SSH_ALLOWED_USER | SSH_EMPTY_PASSWD_ENABLED | USER_SHELL_VALID | USER_PASSWD_BLANK)): return True

        if ((self.login_flags & (SSH_ALLOWED_USER | SSH_PUBKEY_ENABLED | USER_SHELL_VALID | USER_SSH_PUBKEY_EXISTS))
                             == (SSH_ALLOWED_USER | SSH_PUBKEY_ENABLED | USER_SHELL_VALID | USER_SSH_PUBKEY_EXISTS)): return True

        return False


# the local host we're running on
class Host:
    # constructor
    def __init__(self, hostname='localhost'):
        self.hostname = hostname


    # TODO: looks for services with a daemon socket
    def getListeningServices(self):
        pass


    # parses specific values from sshd_config, to see if users can login
    def getSshdConfig(self, usersList, localSystem):
        allowusers_line_found = False
        configLinesRegex = {}
        configLinesRegex['AllowUsers'] = re.compile(r'^AllowUsers\s(?P<users>.*)$')
        configLinesRegex['PermitRootLogin'] = re.compile(r'^PermitRootLogin\s(?P<root>.*)$')
        configLinesRegex['PermitEmptyPasswords'] = re.compile(r'^PermitEmptyPasswords\s(?P<empty>.*)$')
        configLinesRegex['PubkeyAuthentication'] = re.compile(r'^PubkeyAuthentication\s(?P<pubkey>.*)$')
    
        try:
            fSsh = open("/etc/ssh/sshd_config", 'r')
        except:
            sys.stderr.write("WARNING: file [/etc/ssh/sshd_config] doesn't exist or could not be opened! Results may not be accurate!\n")
            return 1
    
        # get SSH config lines
        sshdData = fSsh.readlines()
        for line in sshdData:
            for regexName in sorted(configLinesRegex.keys()):
                m = configLinesRegex[regexName].match(line)
    
                # if user is one of the AllowUsers
                if m and regexName == 'AllowUsers':
                    allowusers_line_found = True
                    tmpUsers = m.group('users').split()
                    for user in tmpUsers:
                        try:
                            # handle 'user@host' form
                            (u, h) = user.split("@")
                            if usersList.has_key(u):
                                usersList[u].login_flags = usersList[u].login_flags | SSH_ALLOWED_USER
                        except:
                            if usersList.has_key(user):
                                usersList[user].login_flags = usersList[user].login_flags | SSH_ALLOWED_USER
   
                # if root login permitted, toggle login flag
                elif m and regexName == 'PermitRootLogin':
                    if usersList.has_key('root'):
                        usersList['root'].login_flags = usersList['root'].login_flags | SSH_ROOT_LOGIN_ENABLED
                        if m.group('root').lower().strip() == 'yes' or m.group('root').lower().strip() == 'true':
                            usersList['root'].login_flags = usersList['root'].login_flags | SSH_ALLOWED_USER

                # if empty passwords enabled, toggle flag for all users 
                elif m and regexName == 'PermitEmptyPasswords':
                    if m.group('empty').lower().strip() == 'yes' or m.group('empty').lower().strip() == 'true':
                        for u in usersList:
                            usersList[u].login_flags = usersList[u].login_flags | SSH_EMPTY_PASSWD_ENABLED
                 
                # if SSH public key auth is permitted
                elif m and regexName == 'PubkeyAuthentication':
                    if m.group('pubkey').lower().strip() == 'yes' or m.group('pubkey').lower().strip() == 'true':
                        for u in usersList:
                            usersList[u].login_flags = usersList[u].login_flags | SSH_PUBKEY_ENABLED
        fSsh.close()

        ## no AllowUsers line found in config, so all are allowed
        if not allowusers_line_found:
            for u in usersList:
                usersList[u].login_flags = usersList[u].login_flags | SSH_ALLOWED_USER
 

    # looks for users with valid shells/passwords, checks for SSH login ability, 
    # and populates the database info for the users.
    def getUserData(self, usersList):
        f = open("/etc/passwd", 'r')
        fs = open("/etc/shadow", 'r')
        nonShells = re.compile(r'^[\S\/]+(false|nologin|sync)$')
        nonPasswords = re.compile(r'^[\!\*]+.*')
        
        # get users with valid shells
        passwdData = f.readlines()
        for line in passwdData: 
            splitData = line.split(":")
    
            usersList[splitData[0]] = LocalUser(splitData[0], "", splitData[5], splitData[6].strip())
            
            m = nonShells.match(splitData[6])
            if not m:
                usersList[splitData[0]].login_flags = usersList[splitData[0]].login_flags | USER_SHELL_VALID 
        
        # get users with valid passwords
        shadowData = fs.readlines()
        for line in shadowData: 
            splitData = line.split(":")
            m = nonPasswords.match(splitData[1])
            if not m:
                if usersList.has_key(splitData[0]):
                    usersList[splitData[0]].password = splitData[1]
                    if splitData[1] == '': usersList[splitData[0]].login_flags = usersList[splitData[0]].login_flags | USER_PASSWD_BLANK
                    else: usersList[splitData[0]].login_flags = usersList[splitData[0]].login_flags | USER_PASSWD_VALID
        f.close()
        fs.close()
        
    
    # looks for users' SSH keys, and checks authorized_keys entries
    # TODO: handle AuthorizedKeysFile line in config
    def getSshAuthorizedKeys(self, usersList):
        authKeysPaths = []    
        commentReg = re.compile("^[\S]{0,}#+")
    
        for user in usersList.keys():
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
                        if status == 0:
                            usersList[user].ssh_authorized_keys.append(fingerprint)
                            usersList[user].login_flags = usersList[user].login_flags | USER_SSH_PUBKEY_EXISTS
                        tmpFile.close()
            
                    f.close()
                except IOError:
                    pass
                authKeysPaths = []



#########################
###  BEGIN EXECUTION  ###
#########################

# holds all the info about discovered users
usersList = {}
localSystem = Host('localhost')

localSystem.getUserData(usersList)
localSystem.getSshdConfig(usersList, localSystem)
localSystem.getSshAuthorizedKeys(usersList)

# print users who can login
print "Valid Accounts with SSH Privileges:"
for user in sorted(usersList.keys()):
    if usersList[user].canLogin():
        print "\t" + usersList[user].name 
print ""

# print keys for users
for user in sorted(usersList.keys()):
    if usersList[user].canLogin() and ((usersList[user].login_flags & USER_SSH_PUBKEY_EXISTS) == USER_SSH_PUBKEY_EXISTS):
        print "Found SSH authorized_keys for user [%s]..." % user
        for key in usersList[user].ssh_authorized_keys:
            print "\t" + key
print "\n"

