#!/usr/bin/perl -w
# 
# @brief  
# A simple script to partially automate backups to a LUKS encrypted disk.
#
# @details
# This script will prompt for a LUKS password, decrypt the LUKS volume, 
# mount it locally, then begin copying files to the volume. Once copying 
# is complete, it will unmount & re-lock the volume.
#
# @author: Devin Cherry <youshoulduseunix@gmail.com>
#
# @todo 
# Error-handling could always be improved...
#########################################################################
use POSIX qw(geteuid);
if(geteuid() != 0) { die("You must run this script as root!\n"); }

# @var $driveName	the logical name to give the LUKS encrypted 'drive'
$driveName = "USB_Backup_Drive";

# @var $target		the location on the filesystem to mount the LUKS volume at
$target = "/mnt/" . $driveName;

# @var $sources		the source files to be copied to the LUKS volume via rsync
$sources = "/mnt/local_backups/*";

# @var $diskDevice	the device mapping of your luks-encrypted drive
$diskDevice = "/dev/sdb1";


# --------------[ BEGIN EXECUTION ]------------
# decrypt the volume
$ret = system("/sbin/cryptsetup luksOpen $diskDevice $driveName");
if(($ret >> 8) != 0) {
        die("Error decrypting drive [$driveName]! Bad password?\n");
}
print("Decrypted LUKS volume [$driveName]\n");

# mount the decrypted volume
$ret = system("/bin/mount -o acl,user_xattr,dev,suid /dev/mapper/$driveName $target");
if(($ret >> 8) != 0) {
        print("Error mounting drive!\n\nDecrypted Volume Status for [$driveName]:\n");
        system("/sbin/cryptsetup status $driveName");
        system("/sbin/cryptsetup luksClose $driveName");
        die("\nDying...\n");
}
print("Mounted LUKS volume [$driveName] at [$target]\n");
sleep(2);
print("Copying files [$sources] to [$target]...\n");

#
# @attention
# The line below which executes the rsync copy is commented out by default!
# This allows the admin to test their variable settings before actually copying files.
# To enable actual file copy, uncomment/modify the following line in the code:
# $ret = system("/usr/bin/rsync -a --stats --acls --xattrs --delete-during $sources $target");
#
print("/usr/bin/rsync -a --stats --acls --xattrs --delete-during $sources $target");
#$ret = system("/usr/bin/rsync -a --stats --acls --xattrs --delete-during $sources $target");
if(($ret >> 8) != 0) {
        die("Error copying files to drive!\n");
}

# give us a while for USB IO to finish before attempting dismount
sleep(120);

print("Done copying files. Unmounting Drive...\n");

# unmount the decrypted volume
$ret = system("/bin/umount $target");
if(($ret >> 8) != 0) {
        print("Error unmounting drive!\n\nDecrypted Volume Status for [$driveName]:\n");
        system("/sbin/cryptsetup status $driveName");
        die("\nDying...\n");
}
sleep(10);

# close the crypto volume
$ret = system("/sbin/cryptsetup luksClose $driveName");
if(($ret >> 8) != 0) {
        die("Error closing volume [$driveName]!\n");
}
print("LUKS volume [$driveName] successfully unmounted & locked.\n");
print("Backup complete.\n");
