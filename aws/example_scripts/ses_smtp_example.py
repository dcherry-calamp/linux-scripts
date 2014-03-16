#!/bin/env python2.6
import smtplib, time

# fromaddr must be from an email that looks like it comes from our domain (i.e. *****@ourdomain.com)
fromaddr = 'frob@somedomain.com'
toaddr  = 'bork@somedomain.com'

header = ("From: %s\r\nTo: %s\r\n"
         % (fromaddr, toaddr))

server = smtplib.SMTP(host='email-smtp.us-east-1.amazonaws.com', port=587)
server.set_debuglevel(1)
server.ehlo()
server.starttls()
server.login('AKIA............','<REDACTED>')

# test send rate limits
maxRate = 0.20
numToSend = 10
for i in range(numToSend):
    time.sleep(maxRate)
    subj = "Subject: test %d\r\n\r\n" % i
    msg = header + subj + "testing..."
    server.sendmail(fromaddr, toaddr, msg)

server.quit()

