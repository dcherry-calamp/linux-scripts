#!/bin/bash

servers='
127.0.0.1
'

for srv in $servers; do
	# get installed rpms
	ssh root@${srv} "rpm -qa; exit" | tee ~/${srv}_rpms-installed.log

	# list local software
	ssh root@${srv} "find /usr/local/{bin,sbin} -type f -perm /u+x; exit" | tee ~/${srv}_local-binaries.log

	# get local changes; verify rpms
	ssh root@${srv} "rpm -qa --verify; exit" | tee ~/${srv}_rpm-verify.log

	# collect all crontabs
	ssh root@${srv} "echo \"/etc/crontab:\"; cat /etc/crontab; for f in \$(find /var/spool/cron/ -type f); do echo \"\$f:\"; cat \$f; done; exit" | tee ~/${srv}_all-crontabs.log

	# get network info
	ssh root@${srv} "hostname -f; exit" | tee ~/${srv}_network_config.log

done
