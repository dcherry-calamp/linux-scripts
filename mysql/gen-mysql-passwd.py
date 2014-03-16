#!/bin/env python2.6
import hashlib 
import getpass

print '*' + hashlib.sha1(hashlib.sha1(getpass.getpass("Enter Your Password: ")).digest()).hexdigest().upper()
