#!/bin/bash
#
# Description:
# user-data script to be passed to ec2run command when spawning a new instance.
#
# TODO:
# - You *MUST* modify the variables SERV_TYPE & AZ below before passing this to ec2run!
# - You'll probably want to modify the section for creating LVM volumes below.
#
# Author: Devin Cherry <youshoulduseunix@gmail.com>
#############################################

# give us some verbose output 
set -x

# MODIFY THESE !!!
SERV_TYPE="foo"
AZ="us-east-1a"
SUBNET="10.0."


##################
# FIXME: these will break if multiple interfaces exist on the host
IP_ADDR=`ifconfig | grep "inet addr:${SUBNET}" | awk '{print \$2}' | awk -F: '{print \$2}'`
HOSTNAME_SHORT="${SERV_TYPE}-`ifconfig | grep "inet addr:${SUBNET}" | awk '{print \$2}' | awk -F: '{print \$2}' | sed 's/\./-/g'`"
HOSTNAME_FQDN="${HOSTNAME_SHORT}.${AZ}.foo.bar"
MEMTOTAL=`awk '{if(\$1 ~ /MemTotal/) {print (\$2 / 1024 * 1.5)}}' /proc/meminfo`

## set up yum proxy (AIS, for now...)
echo 'proxy=http://rpm.mycompany.com:80/' >> /etc/yum.conf

## properly configure the hostname 
sed -i "s/^HOSTNAME=.*\$/HOSTNAME=$HOSTNAME_FQDN/" /etc/sysconfig/network
hostname $HOSTNAME_FQDN
echo "$IP_ADDR $HOSTNAME_FQDN $HOSTNAME_SHORT" >> /etc/hosts

## point to local puppetmaster 
echo '192.168.1.99 puppet.mycompany.com' | tee -a /etc/hosts



##################################################################################################
#      EDIT LVM VOLUMES & MOUNTS
##################################################################################################

### create some LVM volumes on ephemeral disk (specified as /dev/sdb, but enumerates in centos as sdf)
#
# TODO: Maybe this could be added to a startup script which tests for existence of these partitions 
#       & recreates them in the case of ephemeral volume failure?
#
## create less important volumes on ephemeral storage 
pvcreate /dev/sdf
vgcreate -v ephemeral /dev/sdf

lvcreate -v -n lv_mntfoo -l 100%FREE ephemeral
mkfs.ext4 /dev/ephemeral/lv_mntfoo
tune2fs -c 0 /dev/ephemeral/lv_mntfoo
echo "/dev/mapper/ephemeral-lv_mntfoo   /mnt/foo  ext4   defaults   0  0" >> /etc/fstab
mount -t ext4 /dev/ephemeral/lv_mntfoo /mnt/foo
chmod 1777 /mnt/foo
restorecon -r /mnt/foo


### Create some LVM volumes on a secondary EBS disk 
### (specified in ec2run as /dev/sdd, but enumerates in centos as sdh)
#
## create home directory on vg01/sdh 
pvcreate /dev/sdh
vgcreate -v vg01 /dev/sdh

lvcreate -v -n lv_swap -L ${MEMTOTAL}M vg01
mkswap /dev/vg01/lv_swap
echo "/dev/mapper/vg01-lv_swap   none   swap   sw         0  0" >> /etc/fstab
swapon -a

lvcreate -v -n lv_home -l 100%FREE vg01
mkfs.ext4 /dev/vg01/lv_home
tune2fs -c 0 /dev/vg01/lv_home
echo "/dev/mapper/vg01-lv_home   /home  ext4   defaults   0  0" >> /etc/fstab
mount -t ext4 /dev/vg01/lv_home /home
restorecon -r /home


### create optional additional volumes on vg02...
#pvcreate /dev/sdi
#vgcreate -v vg02 /dev/sdi
#lvcreate -v -n lv_opt -L 100G vg02
#mkfs.ext4 /dev/vg02/lv_opt
#tune2fs -c 0 /dev/vg02/lv_opt
#echo "/dev/mapper/vg02-lv_opt   /opt  ext4   defaults   0  0" >> /etc/fstab
#mount -t ext4 /dev/vg02/lv_opt /opt
#restorecon -r /opt
#
#lvcreate -v -n lv_data2 -l 100%FREE vg02
#mkfs.ext4 /dev/vg02/lv_data2
#tune2fs -c 0 /dev/vg02/lv_data2
#echo "/dev/mapper/vg02-lv_data2   /data2  ext4   defaults   0  0" >> /etc/fstab
#mkdir /data2
#mount -t ext4 /dev/vg02/lv_data2 /data2
#restorecon -r /data2
#
#################################################################################################


### now that we have a hostname, let's request a puppet cert!
/usr/sbin/puppetd --test --server=puppet.mycompany.com --tags=puppet --waitforcert 60

