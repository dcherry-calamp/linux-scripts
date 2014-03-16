#!/bin/bash
#
# Simple script to check LSI RAID controllers for failed arrays.
# If any controller is found to have a BAD array, this script returns
# the highest-criticality value found. i.e. Any CRITICAL state trumps
# any WARNING state which trumps any UNKNOWN state.
#
# Author: Devin Cherry <youshoulduseunix@gmail.com>
######################################################################

tw_cli=/usr/local/bin/tw_cli
if [ ! -x ${tw_cli} ]; then
    echo "ERROR: Could not execute file [${tw_cli}]!"
    exit 3
fi

# get list of controllers
controllers=`sudo ${tw_cli} show | awk '{if($1 != "Ctl" && $1 != "Enclosure" && $1 !~ /^\// && NF > 5){print $1}}'`
if [[ ${controllers} < 1 ]]; then
    echo "ERROR: Failed to find any LSI controllers!"
    exit 3
fi
RET=0

# enumerate controllers, checking for non-OK arrays
for c in ${controllers}; do
    units=$(sudo ${tw_cli} /${c} show unitstatus | egrep -v "^(Unit|---)" | awk '{if(NF > 2){print}}')
    units_ok=$(echo "${units}" | awk '{if($3 ~ /(OK|VERIFYING)/){print}}' | wc -l)
    # VERIFY-PAUSED should only appear if other units are currently VERIFYING.
    units_bad=$(echo "${units}" | awk '{if($3 !~ /(OK|VERIFY)/){print}}' | wc -l)

    # check for UNK states first, so the more important CRIT|WARN states will trump UNK
    if [[ ${units} < 1 || (${units_ok} -lt 1 && ${units_bad} -lt 1) ]]; then
        echo "Controller /${c} is UNKNOWN: Failed to detect unit states!"

        # only set RET if we're not overriding the value from a previous controller check
        if [[ ${RET} -eq 0 ]]; then
            RET=3
        fi
        continue
    fi

    ## STUB: now check for any WARN states (WARN trumps UNK)
    #if [[ $RET -eq 0 || $RET -eq 3 ]]; then
    #    RET=1
    #fi

    # now check for any CRIT states 
    if [[ ${units_bad} -gt 0 ]]; then
        echo "Controller /${c} is CRITICAL: ${units_bad} unit(s) in non-OK state!"
        RET=2
    else
        echo "Controller /${c} is OK: ${units_ok} unit(s) in OK state."
    fi
done

exit ${RET}

