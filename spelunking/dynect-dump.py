#!/bin/env python2.6
#
# Get a list of all CNAME & A records for a set of our domains.
###
import sys, getpass, string
from dynect.DynectDNS import DynectRest   # API module available from dynect site

print "Username: ",
user = sys.stdin.readline(80).rstrip()
passwd = getpass.getpass("Password: ")
login_args = { 'customer_name': 'mycompany',
               'user_name': user,
               'password': passwd, }

zones = [ u'/AllRecord/mycompany.net/', u'/AllRecord/mycompany.co.jp/', 
          u'/AllRecord/mycompany.com/', ]

try:
    rest_iface = DynectRest()
    response = rest_iface.execute('/Session/', 'POST', login_args)
    if response['status'] != 'success':
        sys.exit("Incorrect credentials")
    
    for zone in zones:
        response = rest_iface.execute(zone, 'GET')
        zone_resources = response['data']
        print "\nrecord_type\trecord\t\ttarget"
        for resource in zone_resources:
            res = rest_iface.execute(resource, 'GET')
            rtype = string.lower(res['data']['record_type'])
            if rtype == 'cname':
                print "%s\t%s\t\t%s" % \
                      ( res['data']['record_type'], res['data']['fqdn'], res['data']['rdata'][rtype] )
            elif rtype == 'a':
                print "%s\t%s\t\t%s" % \
                      ( res['data']['record_type'], res['data']['fqdn'], res['data']['rdata']['address'] )

except Exception as e:
    sys.stderr.write("ERROR: %s\n" % e)
finally:
    # Log out, to be polite
    rest_iface.execute('/Session/', 'DELETE')

