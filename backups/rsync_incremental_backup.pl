#!/usr/bin/perl -w
# 
# @brief 
# A script to perform incremental filesystem backups, using rsync-over-SSH.
#
# @details 
# Performs rsync-over-ssh backup of specified hosts.
# A directory named after your host (the 'key' in the %src_database table), 
# will be created in the $backups_base directory. Or, if it already 
# exists, that directory will be used instead, and snapshots will be 
# rotated/created with an increment appended to the directory name.
#
# Usage: Modify these variables to get the desired affect. Places
#        where you put a "hostname", "server", etc... will take a
#        resolvable name only. IPv4 addresses should work too.
#
#   $backups_base - Specifies the base directory to place your
#                   backup directory (and sub-files) in.
#
#   $snapshot_dir - Specifies the subdirectory to place snapshot rotations
#                   in. Specify "" to put them in the same directory.
#
#   $ssh_cmd      - The SSH command-line prefix. You can modify the 
#                   remote username here.
#
#   $rsa_keys_dir - The directory holding your rsa key-pair for
#                   remote login. The public key should be in
#                   authorized_keys on the remote host. NOTE: ensure 
#                   the <server> portion of the rsa keys match
#                   the servername you enter in %src_database!
#
#   $bw_limit     - The bandwidth usage limit (in KBytes/s) to use
#                   during file transfer.
#
#   %src_database - The list of hosts (keys), and files/directories
#                   (values) to archive.
#
#   $num_snapshots - The number of revisions, including current, to
#                    keep backed up. These work as daily diffs. Use
#                    the create_snapshot.pl script to create a 
#                    snapshot of changes back to a particular date.
# 
# @author Devin Cherry <youshoulduseunix@gmail.com>
#
# @todo	better error handling; better config options; ...
################################################################################

# NOTE: change $backups_base, $rsa_keys_dir to absolute paths once installed!
$backups_base = "/mnt/local_backups"; # base location for backups
$snapshot_dir = "snapshots_nightly"; # don't append/prepend a "/"
$ssh_cmd = "/usr/bin/ssh -l root -i"; # probably shouldn't edit this...
$rsa_keys_dir = "/someplace/scripts/backups/ssh_keys/"; # keys are named "id_rsa_<server>"
$bw_limit = "8000"; # prevent saturation of slow network links
$num_snapshots = 7; # incremental snapshots to keep/rotate. 

# Put your server and list of files/directories here.
%src_database = (
	serverA => ["/root", "/bin", "/dev", "/etc", "/lib", "/lib64", "/opt", "/sbin", "/srv", "/usr", "/var", "/boot", "/vmlinuz", "/vmlinuz.old", "/initrd.img", "/initrd.img.old", "/home"],
	serverB => ["/root", "/bin", "/dev", "/etc", "/lib", "/lib64", "/opt", "/sbin", "/srv", "/usr", "/var", "/boot", "/vmlinuz", "/vmlinuz.old", "/initrd.img", "/initrd.img.old", "/home"],
);

###################[ END MODIFIABLE VARIABLES ]##################

$date = `/bin/date +%F_%k-%M-%S`;
chomp($date);
print("-- Starting rsync backups, $date --\n");

# for each host, generate an rsync source list, and run rsync for those files
for $src_host (keys %src_database) {
	$host_key = $rsa_keys_dir . "id_rsa_" . "$src_host";
	if( -f $host_key ) {
		print("Backing up [$src_host] to $backups_base...\n");

		# build rsync source files list
		$src_list = "";
		foreach $file ( @{$src_database{$src_host}} ) {
			$src_list .= (" root\@" . $src_host . ":" . $file);
		}

		# rotate existing directories; remove oldest version if >= $num_snapshots
		for( $inc = $num_snapshots; $inc >= 0; $inc-- ) {
			$inc_plus = $inc + 1;

			# if snapshot exists
			if( -e "$backups_base/$snapshot_dir/$src_host-$inc" ) {
				# if snapshot is older than allowed, remove it.
				if($inc >= $num_snapshots) {
					system("/bin/rm -rf $backups_base/$snapshot_dir/$src_host-$inc\n");
	
					$tmp_var = ($? >> 8); # get stderr from previous command
					if( $tmp_var > 0 ) {
						print(STDERR "\n\tERROR: unable to remove old snapshot -- error status: $tmp_var!\n\n");
					}
				} else {
					system("/bin/mv $backups_base/$snapshot_dir/$src_host-$inc $backups_base/$snapshot_dir/$src_host-$inc_plus\n");
					$tmp_var = ($? >> 8); 
					if( $tmp_var > 0 ) {
						print(STDERR "\n\tERROR: unable to rotate old snapshot -- error status: $tmp_var!\n\n");
					}
				}
			}

		}

		# perform rsync of changed files
		$backup_dir = "$backups_base/$snapshot_dir/$src_host-0";
		system("/usr/bin/rsync --bwlimit=$bw_limit -baiR --delete --acls --xattrs --backup-dir=$backup_dir -e \"$ssh_cmd $host_key\"$src_list $backups_base/$src_host/\n");

		$ret = ($? >> 8); 
		if( $ret > 0 ) {
			print(STDERR "\n\tERROR: rsync returned error status: $ret!\n\n");
		}
	} else { 
		print(STDERR "\n\tERROR: $src_host SSH keys not found, skipping backup!\n\n");
	}
}

exit(0);

