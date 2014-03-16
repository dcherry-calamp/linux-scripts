#!/bin/bash
#
# Simple script to check Adaptec RAID controllers for failed arrays.
#
# Author: Devin Cherry <youshoulduseunix@gmail.com>
######################################################################

raid_util=/usr/local/bin/arcconf
if [ ! -x ${raid_util} ]; then
    echo "ERROR: Could not execute file [${raid_util}]!"
    exit 3
fi

RET=0
units_ok=0
units_bad=0
controllers=$(sudo ${raid_util} GETVERSION | awk '{if($1 == "Controller"){ print $2 }}' | cut -d'#' -f2)

# Since there's no command to list known controllers, we have to blindly enumerate them...
for ctrlr in ${controllers}; do
    tmp_units_ok=$(sudo ${raid_util} GETCONFIG ${ctrlr} LD | awk -F':' '{if($1 ~ /Status of logical device/){print $2}}' | awk '{if($1 ~ /Optimal/){print}}' | wc -l)
    units_ok=$(expr ${units_ok} + ${tmp_units_ok})
    tmp_units_bad=$(sudo ${raid_util} GETCONFIG ${ctrlr} LD | awk -F':' '{if($1 ~ /Status of logical device/){print $2}}' | awk '{if($1 !~ /Optimal/){print}}' | wc -l)
    units_bad=$(expr ${units_bad} + ${tmp_units_bad})
done

# check for UNK states first, so the more important CRIT|WARN states will trump UNK
if [[ ${units_ok} -lt 1 && ${units_bad} -lt 1 ]]; then
    echo "Adaptec RAID is UNKNOWN: Failed to detect any logical drives!"
    exit 3
fi

## STUB: now check for any WARN states (WARN trumps UNK)
#if [[ $RET -eq 0 || $RET -eq 3 ]]; then
#    RET=1
#fi

# now check for any CRIT states 
if [[ ${units_bad} -gt 0 ]]; then
    echo "Adaptec RAID is CRITICAL: ${units_bad} virtual drive(s) in non-Optimal state!"
    RET=2
else
    echo "Adaptec RAID is OK: ${units_ok} virtual drive(s) in Optimal state."
    RET=0
fi

exit ${RET}

