#!/bin/env python2.6
# 
# Description:
#   Reads a Ganglia events.json file, and truncates it to the most recent 2-weeks
#   of events, archiving all older events in an archive file.
#
# Author: Devin Cherry <youshoulduseunix@gmail.com>
#################################################################################
import sys, fcntl, traceback, time
import json


gangliaEventsFile = '/var/lib/ganglia/conf/events.json'


#################################################################
#                             BEGIN                             #
#################################################################

# deal with the mixed encoding issue in the ganglia-generated json 
def encode_object_as_ascii(pyObj):
    ascii_encoded = lambda x: str(x).encode('ascii')
    return dict(map(ascii_encoded, pair) for pair in pyObj.items())


try:
    eventsFile = open(gangliaEventsFile, 'rw+')
    fcntl.lockf(eventsFile, fcntl.LOCK_SH)
    data = eventsFile.read()

    # decode the json as python nested objects (this turns into a list of dictionaries in this case),
    # and sort the list by nested value 'start_time'
    eventsList = json.loads(data, object_hook=encode_object_as_ascii)
    sortedEventsList = sorted(eventsList, key=lambda event: event['start_time'])

    # get the index of the most recent event from two weeks ago
    index = -1
    for event in sortedEventsList[::-1]:
        if (time.time() - float(event['start_time'])) > 1209600:
            break
        index = index - 1

    # get the truncated list, including everything from last two weeks
    archiveEvents = sortedEventsList[0:index]
    recentEvents = sortedEventsList[index:]

    # archive old events
    archiveFileName = gangliaEventsFile + '.archived.' + str(time.time()).split('.')[0]
    newFile = open(archiveFileName, 'w')
    newFile.write(json.dumps(archiveEvents))
    newFile.close()

    # truncate events file, rewriting only recent events to it
    eventsFile.seek(0)
    eventsFile.truncate()
    eventsFile.write(json.dumps(recentEvents))
    fcntl.lockf(eventsFile, fcntl.LOCK_UN)
    eventsFile.close()

    print "Archived all but most recent %d events into file [%s]." % (len(recentEvents), archiveFileName)

except Exception, e:
    print traceback.format_exc()
    sys.exit(1)
sys.exit(0)


