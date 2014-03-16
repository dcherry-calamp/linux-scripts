#!/bin/bash
#
# Description: A simple tool to quickly get lots of info from a cluster of systems.
#
# Author: Devin Cherry <youshoulduseunix@gmail.com>
######################################################################################

if [ "$1" == "" -o "$1" == "-h" -o "$2" == "" ]; then
    echo "usage: $0 <status|config> <clusterit_group>"
    echo ""
    echo "Current Groups:"
    echo "---------------"
    egrep "^(GROUP|LUMP)" /etc/clusterit.conf | awk -F':' '{print $2}' | sort -u
    exit 1
fi
option="$1"
dsh_group="$2"


if [ "$option" == "config" ]; then
    echo "Getting Sysctl: TCP memory limits (in pages)..."
    dsh -e -g$dsh_group -- "sudo cat /proc/sys/net/ipv4/tcp_mem" | sort
    
    echo "Getting Sysctl: Orphaned TCP connections limit..."
    dsh -e -g$dsh_group -- "sudo cat /proc/sys/net/ipv4/tcp_max_orphans" | sort

elif [ "$option" == "status" ]; then
    echo "Getting Server Stat: Uptime/Load..."
    dsh -e -g$dsh_group -- "uptime" | sort

    echo "Getting Server Stat: Memory used/freeable (MB)..."
    dsh -e -g$dsh_group -- "free -m | egrep \"[-/+]+\"" | sort

    echo "Getting TCP Stats..."
    dsh -e -g$dsh_group -- "sudo cat /proc/net/sockstat | grep sockets" | sort
    dsh -e -g$dsh_group -- "sudo cat /proc/net/sockstat | grep TCP" | sort
    
    echo "Getting Bad Processes..."
    dsh -g$dsh_group -- "ps aux | awk '{if(\$8 ~ /[ZXD]/){print}}'" | sort
    
    echo "Getting Java Thread Counts..."
    dsh -g$dsh_group -- "ps -eLf | grep -i java | grep -v grep' | wc -l" | sort
    
    echo "Getting Counts for ESTABLISHED DB Connections..."
    dsh -g$dsh_group -- "netstat -atn | grep ":3306 " | grep EST | wc -l" | sort
    
    echo "Getting Counts for TIME_WAIT DB Connections..."
    dsh -g$dsh_group -- "netstat -atn | grep ":3306 " | grep TIME_WAIT | wc -l" | sort

    echo "Getting Ruby Process Counts..."
    dsh -g$dsh_group -- "ps u -C ruby | wc -l" | sort
    
    echo "Getting High-IO Util/Svctm Disks..."
    dsh -g$dsh_group -- "iostat -dkx | grep -v Device | awk '{if(\$10 > 50 || \$12 > 20){ print }}'" | sort
else
    echo "ERROR: invalid option specified..."
    echo "usage: $0 <status|config> <clusterit_group>"
    exit 1
fi
