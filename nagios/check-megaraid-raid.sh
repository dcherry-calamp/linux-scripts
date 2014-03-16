#!/bin/bash
#
# Simple script to check MegaRAID controllers for failed arrays.
# If any controller is found to have a BAD array, this script returns
# the highest-criticality value found. i.e. Any CRITICAL state trumps
# any WARNING state which trumps any UNKNOWN state.
#
# Author: Devin Cherry <youshoulduseunix@gmail.com>
######################################################################

raid_util=/opt/MegaRAID/MegaCli/MegaCli64
if [ ! -x ${raid_util} ]; then
    echo "ERROR: Could not execute file [${raid_util}]!"
    exit 3
fi

RET=0

units=($(sudo ${raid_util} -LDInfo -LALL -aALL -NoLog \
        | awk 'BEGIN { i=0;j=0 } $1 == "State" { if ($3 == "Optimal") {i++} else {j++} } END { print i,j }' \
      ))
units_ok=${units[0]}
units_bad=${units[1]}

# check for UNK states first, so the more important CRIT|WARN states will trump UNK
if [[ ${units_ok} -lt 1 && ${units_bad} -lt 1 ]]; then
    echo "MegaRAID is UNKNOWN: Failed to detect any virtual drives!"
    exit 3
fi

## STUB: now check for any WARN states (WARN trumps UNK)
#if [[ $RET -eq 0 || $RET -eq 3 ]]; then
#    RET=1
#fi

# now check for any CRIT states 
if [[ ${units_bad} -gt 0 ]]; then
    echo "MegaRAID is CRITICAL: ${units_bad} virtual drive(s) in non-OK state!"
    RET=2
else
    echo "MegaRAID is OK: ${units_ok} virtual drive(s) in OK state."
    RET=0
fi

exit ${RET}

