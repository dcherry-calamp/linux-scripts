#!/usr/bin/perl -w
#
# Parses Amazon S3 log files:
#  Iterates thru all files in the specified directory, (or thru the given
#  file if a filename is specified), parsing the file for the specified
#  parameters.
#
# Author: Devin Cherry <youshoulduseunix@gmail.com>
###############################################################################
use strict;
use Getopt::Long;

###############################
#     Our Local Variables     #
###############################

# list of files to be parsed
my @filenames = ();

# user-specified options
my $quiet = '0';
my $debug = '0';
my $printCsv = '0';
my $fieldVal = '';
my $specificValue = '';
my $fieldList = '0';
my $skipSizeCheck = '0';

# used for output printing
my $delimiter = "\t\t";
#my $prog = $ARGV[1];
my $prog = "s3-access-log-parser.pl";

# size limits (in MB) before prompting for confirmation to continue
my $maxSizeSimple = 5000;
my $maxSizeDeep = 275;


####################################
#     Semi-Static AWS Variables    #
####################################

##
#** @brief Field name to field index mapping for PUT operations
#
# Amazon may add additional fields to the *end* of a log entry in the future.
# These fields currently apply to both PUT and GET operations. User-defined
# fields (i.e. x-<fieldname>), are appended.
# (http://docs.aws.amazon.com/AmazonS3/latest/dev/LogFormat.html)
my %fields = (
    BucketOwner => 0,
    Bucket      => 1,
    Time        => 2,  # This field is broken by a space in the middle. Make sure to merge it!
    RemoteIP    => 3,
    Requester   => 4,
    RequestID   => 5,
    Operation   => 6,
    Key         => 7,
    RequestURI  => 8,  # This is an enclosed/quoted string with spaces. i.e. "some uri val"
    HTTPStatus  => 9,
    ErrorCode   => 10,
    BytesSent   => 11,
    ObjectSize  => 12,
    TotalTime   => 13,
    TurnAroundTime  => 14,
    Referrer    => 15, # This is an enclosed/quoted string with spaces. i.e. "some uri val"
    UserAgent   => 16, # This is an enclosed/quoted string with spaces. i.e. "some uri val"
    VersionID   => 17,
);


################################
#       Support Functions      #
################################

# function: print usage info
sub printUsage {
    print "
Usage: $prog <options> [--] <path_to_files>\n
  Output Options:
\t--debug\t\tPrint debug output.
\t--quiet\t\tPrint minimal output.
\t--output-csv\tPrints summary in CSV format.
\n  Parse Options:
\t--field-list\t\tPrint out all recognized fields for summarization.
\t--field <field_name>\tPrint Summary by <field_name> Field.
\t--specific-value <val>\tPrint Summary by a specific value in a field. 
\t\t\t\tA field must be specified so we know what the value means 
\t\t\t\t(i.e. --field Requester --specific-value \"some-user-id\").
\n  Misc. Options:
\t--skip-size-check\tDo not check size of input before parsing.
    \n";
}

##
#** @brief validate running environment 
#   Checks the Operating system to make sure we can run properly.
sub checkEnv {
    my $ret = system("which which 1>>/dev/null");
    if(($ret >> 8) ne 0) { die("ERROR: command 'which' not found\n"); }

    $ret = system("which find 1>>/dev/null");
    if(($ret >> 8) ne 0) { die("ERROR: command 'find' not found\n"); }

    $ret = system("which du 1>>/dev/null");
    if(($ret >> 8) ne 0) { die("ERROR: command 'du' not found\n"); }

    $ret = system("which awk 1>>/dev/null");
    if(($ret >> 8) ne 0) { die("ERROR: command 'awk' not found\n"); }
}

##
#** @brief return total file-size to be parsed in MiB
sub getParseSize {
    my $totalSize = 0;
    my $sz = '';

    # iterate each file passed in array, and get disk size in KiB
    foreach my $file (@{shift(@_)}) {
        $sz = `du -k $file | awk '{print \$1}'`;
        chomp($sz);
        
        $totalSize += $sz;
        if($debug) { print "\tAdding $sz-KiB for file [$file]...\n"; } 
    }

    return $totalSize / 1024;
}


################################
#        Parse Functions       #
################################

#** @brief Return access counts summarized by a specified field
#
#** @param \@filesToParse Array of filenames to parse
#** @param $parseField The name of the log field to summarize
#** @param $specificValue An optional specific value to filter counts by
#** @param $specificValueField An optional field to map the $specificValue to
sub getAccessCountsByField {
    my %tmpFields;
    my $tmp = '';
    my $line = '';
    my $output = '';
    my $firstIteration = '1';

    # grab function arguments
    my @files = @{shift(@_)};
    my $fieldVal = shift(@_);
    my $specVal = shift(@_);
    my $specField = shift(@_);

    # Iterate each file in the list passed to this function,
    # then parse each line for the specific field. Increment a
    # counter for each unique value found.
    foreach my $file (@files) {
        open(my $fh, "<", $file);

        while(readline($fh)) {
            chomp($line = $_);
            if($line eq "") { next; }

            # fix up some fields, so they split cleanly below
            # fixTimestamp must be run before any other parsing occurs!
            $line = fixTimestamp(\$line);
            $line = fixQuotedStringsWithSpaces(\$line);

            # if we were passed the optional last two params, clean up any spaces for matching
            if($specVal and $specField) {
                if($firstIteration and (($specField eq "RequestURI") 
                                        or ($specField eq "Referrer") 
                                        or ($specField eq "UserAgent"))) {
                    $specVal =~ s/ /|||||||||/ig;
                    $specVal = '"' . $specVal . '"';
                    $firstIteration = '0';
                }               
            }
        
            # Split the log entry on space delimiters, then grab the field that 
            # corresponds to the value supplied by the user.
            my @fieldList = split(/ /, $line);
            $tmp = $fieldList[$fields{$fieldVal}];

            # if it's a new value, add it to the hashtable
            if( not exists($tmpFields{$tmp}) ) {
                if($debug) { print "New $fieldVal: $tmp\n"; }
        
                # if they supplied a specific field for drilling into, only add if 
                # the keyed-on field has a match for the value they supplied.
                if($specField and $specVal) {
                    if($fieldList[$fields{$specField}] eq $specVal) {
                        $tmpFields{$tmp} = 1;
                    } else {
                        if($debug) {
                            print "\$fieldList[\$fields{$specField}] contains [" 
                                   . $fieldList[$fields{$specField}] . "]\n";
                            print "\$specVal = [$specVal]\n";
                        }
                        next;
                    }
                } else {
                    $tmpFields{$tmp} = 1;
                }

            # else, increment the existing value
            } else {  
                if($debug) { print "Incrementing $fieldVal: $tmp\n"; }

                # if they supplied a specific field for drilling into, only increment if 
                # the keyed-on field has a match for the value they supplied.
                if($specField and $specVal) {
                    if($fieldList[$fields{$specField}] eq $specVal) {
                        $tmpFields{$tmp}++;
                    } else {
                        next;
                    }
                } else {
                    $tmpFields{$tmp}++;
                }
            }
        }

        close($fh);
    }

    return %tmpFields;
}

##
#** @brief fix quoted string with spaces
#   substitutes spaces in a quoted string with some crazy sequence so other split()
#   operations on the string will parse out the fields properly.
#
#** @param \$string the full log entry line to be 'fixed'
sub fixQuotedStringsWithSpaces {
    my $retLine = '';
    my $substitutedString = '';

    # split the passed-in string on the quote delimiter first
    my @quotedStrings = split(/"/, ${shift(@_)});


    # Fix the "RequestURI" quoted string
    if($quotedStrings[1]) {
        $quotedStrings[1] =~ s/ /|||||||||/ig;
    }

    # Fix the "Referrer" quoted string
    if($quotedStrings[3]) {
        $quotedStrings[3] =~ s/ /|||||||||/ig;
    }

    # Fix the "UserAgent" quoted string
    if($quotedStrings[5]) {
        $quotedStrings[5] =~ s/ /|||||||||/ig;
    }


    # Finally, reassemble the full string we were originally passed
    foreach my $fixedSubstring (@quotedStrings) {
        if($fixedSubstring) {
            $retLine .= $fixedSubstring;
            $retLine .= '"';
        }
    }
    
    # get rid of that pesky extra double-quote
    $retLine =~ s/"$//g;

    if($debug) { print "Patched-up quoted substring: [$retLine]\n"; }
    return $retLine;
}

##
#** @brief unfix quoted string with our previously inserted funky delimiter
#   substitutes crazy sequence in a quoted string with spaces so we can print
#   the original unaltered string.
#
#** @param \$substring the individual field to be reverted back to original format.
sub unfixQuotedStringsWithSpaces {
    my $retLine = ${shift(@_)};

    # replace '|||||||||' with ' '
    $retLine =~ s/\|{9}/ /ig;

    return $retLine;
}

##
#** @brief removes the unnecessary space from the timestamp field in a log entry
#   This must be run before any other parsing is done, since it permanently modifies the 
#   number of fields to be parsed. (shifts them left by one)
#
#** @param \$logEntry the entire original log entry to be fixed
sub fixTimestamp {
    my @tmpFields = split(/ /, ${shift(@_)});
    my $logEntry = '';
    my $counter = 0;
    my $tmpTime = '';    # the left side of the broken Time field

    # rebuild the log entry, merging the left & right sides of the broken Time field
    foreach my $field (@tmpFields) {
        if($counter eq 2) {
            $tmpTime = $field;
        } elsif($counter eq 3) {
            $logEntry .= (' ' . $tmpTime . $field);
        } elsif($counter gt 0) {
            $logEntry .= (' ' . $field);
        } else {
            $logEntry .= $field;
        }
        $counter++;
    }

    # return the concatenation of the two halves of the Time field
    return $logEntry;
}


# ---------------------------
#           BEGIN
# ---------------------------

# parse CLI options
GetOptions('quiet' => \$quiet, 'debug' => \$debug, 'output-csv' => \$printCsv, 
           'skip-size-check' => \$skipSizeCheck, 'specific-value=s' => \$specificValue, 
           'field=s' => \$fieldVal, 'field-list' => \$fieldList);

# validate input & handle some options
if($fieldList) {
    print "Parseable Fields:\n";
    foreach my $f (keys %fields) {
        print "\t$f\n";
    }
    exit 1;
} elsif( $#ARGV lt 0 ) {
    printUsage() and exit(1);
} elsif(not ($fieldVal gt "")) {
    print "ERROR: Please specify a field to parse!\n";
    printUsage() and exit(1);
}
if($printCsv) {
    $delimiter = ",  ";
} 

# validate operating environment
checkEnv();

# grab file/directory name arguments for parsing
foreach my $name (@ARGV) {
    # if it's a file, add it to the list 
    if( -f $name ) {
        chomp($name);
        if(not $quiet) { print "Adding: [$name]\n"; }
        push(@filenames, $name);

    # if it's a directory, recursively add all contained files
    } elsif( -d $name ) {
        my @tmp = `find $name -type f`;
        foreach my $tmpname (@tmp) {
            chomp($tmpname);
            if(not $quiet) { print "Adding: [$tmpname]\n"; }
            push(@filenames, $tmpname);                
        } 
    } else {
        print "ERROR: Please specify valid files or directories to parse!\n";
        printUsage() and exit(1);
    }
}
if($#filenames lt 0) {
    print "ERROR: Please specify valid files or directories to parse!\n";
    printUsage() and exit(1);
}

# check if total size of parsed input is kinda big for the operation
if(not $skipSizeCheck) {
    if(not $quiet) {print "Checking data size for parsing...\n"};
    my $size = getParseSize(\@filenames);

    if((($size > $maxSizeSimple) and not ($specificValue)) 
       or (($size > $maxSizeDeep) and ($specificValue))) {

        print "WARNING: total size of input to be parsed is $size MiB. Proceed (y/n)? ";
        read(STDIN, my $resp, 1);
        if($resp !~ /^[Yy]/) {
            die("quitting...\n");
        } 
    }
}

# print summary by specified field
if( exists $fields{$fieldVal} ) {
    if(not $quiet) {print "Parsing files (this may take a while)...\n";}

    # if the user gave a specific value, they probably want that value's summary report instead 
    if( $specificValue ) {
        print "Access counts keyed on specific-value: [$specificValue]\n";
        print "-----------------------------------------------------------\n";

        # Run counts for all fields, and print summaries matching the supplied specific-value.
        #
        # FIXME: This is horribly inefficient--but then, we don't wanna fill RAM with
        #        a giant hashtable...
        # TODO: allow user to specify the fields to summarize 
        foreach my $key (keys %fields) {
            # get summary counts, filtered by specificValue
            my %myHash = getAccessCountsByField(\@filenames, $key, $specificValue, $fieldVal);

            # print out our summary for this key
            print "\n\n$key" . $delimiter . "Count\n";
            print "------------" . $delimiter . "------\n";
            foreach my $k (keys %myHash) {
                print unfixQuotedStringsWithSpaces(\$k) . $delimiter . "$myHash{$k}\n";
            }           
        }

        # assume we're only printing the big summary by specific supplied key value, so exit.
        exit(0);
    } else {
        my %tmpHash = getAccessCountsByField(\@filenames, $fieldVal);
        print "Access Counts by $fieldVal:\n";
        print $fieldVal . $delimiter . "Count\n";
        print "------------" . $delimiter . "------\n";
        foreach my $key (keys %tmpHash) {
            print unfixQuotedStringsWithSpaces(\$key) . $delimiter . "$tmpHash{$key}\n";
        }
    }
} else {
    print "ERROR: Invalid field specified!\n";
    printUsage() and exit(1);
}

