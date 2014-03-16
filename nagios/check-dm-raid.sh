#!/bin/bash
#
# Simple script to check DM RAID sets for failed arrays.
#
# Author: Devin Cherry <youshoulduseunix@gmail.com>
######################################################################

raid_util=/sbin/dmraid
if [ ! -x ${raid_util} ]; then
    echo "ERROR: Could not execute file [${raid_util}]!"
    exit 3
fi

RET=0

units_ok=$(sudo ${raid_util} -s | awk -F':' '{if($1 ~ /status/){print $2}}' | awk '{if($1 ~ /ok/){print}}' | wc -l)
units_bad=$(sudo ${raid_util} -s | awk -F':' '{if($1 ~ /status/){print $2}}' | awk '{if($1 !~ /ok/){print}}' | wc -l)

# check for UNK states first, so the more important CRIT|WARN states will trump UNK
if [[ ${units_ok} -lt 1 && ${units_bad} -lt 1 ]]; then
    echo "DM RAID is UNKNOWN: Failed to detect any raid sets!"
    exit 3
fi

## STUB: now check for any WARN states (WARN trumps UNK)
#if [[ $RET -eq 0 || $RET -eq 3 ]]; then
#    RET=1
#fi

# now check for any CRIT states 
if [[ ${units_bad} -gt 0 ]]; then
    echo "DM RAID is CRITICAL: ${units_bad} raid sets in non-OK state!"
    RET=2
else
    echo "DM RAID is OK: ${units_ok} raid sets in OK state."
    RET=0
fi

exit ${RET}

