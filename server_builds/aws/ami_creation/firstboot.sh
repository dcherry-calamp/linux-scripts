#!/bin/bash
#
# Description:
# Simple script to download/execute user-data upon first boot of new instance.
#
# Author: Devin Cherry <youshoulduseunix@gmail.com>
################################################################################
set -x
exec 2> /var/local/firstboot.log

# get user-data 
RETRY=0
while [ ! -s /tmp/Ui8123gvaqlkd_userdata.sh ] && [ $RETRY -lt 5 ]; do
	sleep 2
	curl -sf http://169.254.169.254/latest/user-data > /tmp/Ui8123gvaqlkd_userdata.sh
	RETRY=`expr $RETRY + 1`
done

# if we got user-data, then execute it as a bash script
if [ -s /tmp/Ui8123gvaqlkd_userdata.sh ]; then
       /bin/chmod -v +x /tmp/Ui8123gvaqlkd_userdata.sh
       /bin/bash /tmp/Ui8123gvaqlkd_userdata.sh
       if [ "$?" == 0 ]; then
               echo "User-data script completed successfully."
               /bin/rm -vf /tmp/Ui8123gvaqlkd_userdata.sh
               exit 0
       else
               echo "WARNING: user-data script exited with non-zero status"
               /bin/mv -v /tmp/Ui8123gvaqlkd_userdata.sh /root/FAILED_USERDATA
               exit 1
       fi
else
	/bin/rm -f /tmp/Ui8123gvaqlkd_userdata.sh
	echo "user-data not available for this instance"
fi

