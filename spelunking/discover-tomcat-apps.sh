#!/bin/bash
# 
# attempt to connect to tomcat manager to get a list of apps for this server.
###

users='
tomcat
java
'
ports='
80
8080
'

# try to get the username/password from the standard auth file
username=$(grep "username=" /some/path/tomcat-users.xml | awk '{if($2 ~ /username=/ && $3 ~ /password=/){print $2}}' | cut -d':' -f1 | cut -d'"' -f2)
password=$(grep "username=" /some/path/tomcat-users.xml | awk '{if($2 ~ /username=/ && $3 ~ /password=/){print $3}}' | cut -d':' -f1 | cut -d'"' -f2)

for user in $users; do
    contexts=$(find /home/${user}/ -type f -iname 'server.xml' -exec grep appBase '{}' \; 2>/dev/null | awk '{for(i=1; i<=20; i++){ if($i ~ /name=/){print $i}}}' | cut -d= -f2 | cut -d'"' -f2)
    for context in $contexts; do
        for port in $ports; do
            apps=$(curl --connect-timeout 3 -HHost:${context} "http://${username}:${password}@localhost:${port}/manager/list" 2>/dev/null | grep -v "^OK ")
            if [ "$?" == "0" ]; then
                for app in $apps; do 
                    printf "${app}\n" 
                done
            fi
        done
    done
done
