#!/bin/env python2.6
#
# Description:
#   A simple logger bot, which sends announcements to XMPP multi-user chat rooms.
#
# Author: Devin Cherry <youshoulduseunix@gmail.com>
######################################################
import sys
import xmpp     # xmpppy package, available via pip
from optparse import OptionParser

# defaults (in case no CLI arguments are given)
bot_jid = 'devops-bot@jabber.mycompany.com'
bot_pass = 'check-passwd-safe'
target_muc = 'foo@jabber.mycompany.com'
userMessage = 'I am a bot.'


## Begin execution
try: 
    parser = OptionParser()
    parser.add_option("-m", "--message", type="string", dest="message", help="The message to send to the target MUC.", default=userMessage)
    parser.add_option("-j", "--jid", type="string", dest="jid", help="The JID to authenticate with.", default=bot_jid)
    parser.add_option("-p", "--password", type="string", dest="password", help="The password to authenticate with.", default=bot_pass)
    parser.add_option("-c", "--muc", type="string", dest="muc", help="The XMPP multi-user chat jid to send the message to.", default=target_muc)
    (options, args) = parser.parse_args()

except:
    sys.exit(1)

 
# Create jid & client object
jid = xmpp.protocol.JID(options.jid)
client = xmpp.Client(jid.getDomain(),debug=[])

# setup the server connection & authenticate via TLS/SASL
client.connect()
client.auth(jid.getNode(), options.password)

# configure for Multi-User Chat
target = options.muc + '/' + options.jid.split('@')[0]
p = xmpp.Presence(to=target)
p.setTag('x', namespace=xmpp.NS_MUC).setTagData('password', options.password)
client.send(p)

# setup the message
msg = xmpp.protocol.Message(body=options.message)
msg.setTo(options.muc)
msg.setType('groupchat')

# finally, send the message to the MUC
client.send(msg)
print "XMPP notification sent..."
client.disconnect()

