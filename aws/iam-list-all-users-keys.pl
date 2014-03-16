#!/usr/bin/perl -w
#
# Description:
#    Prints a list of all users & keys for an aws account.
#    Requires that the current env have the account's credentials, per Amazon's
#    iam tools documentation. (i.e. should be able to run 'iam-userlistbypath')
#
# Author: Devin Cherry <youshoulduseunix@gmail.com>
###############################################################################


# show the current env's AWS config
print "Using Environment:\n";
$curr_key = `env | grep AWS_ACCESS_KEY`;
$curr_cred_file = `env | grep AWS_CREDENTIAL_FILE`;
print "   $curr_key   $curr_cred_file\n";


# enumerate all users+keys
@allusers = `iam-userlistbypath`;
foreach $userline (@allusers) {
    # get just the username at the end of the path
    @userfields = split(/\//, $userline);

    if($#userfields >= 1) {
        chomp($userfields[1]);

        # now iterate keys for this user
        @keys = `iam-userlistkeys -u $userfields[1]`;
        foreach $key (@keys) {
            # keys are always 20-chars long, plus null terminator
            if(length($key) == 21) {
                chomp($key);
                printf("\n%s\t\t%s", $userfields[1], $key);
            }
        }
    }
}

print "\n\n";
