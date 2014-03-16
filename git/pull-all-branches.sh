#!/bin/bash
#
# Pulls all branches from all Git repos in the current directory.
###

# FIXME: will list hidden dirs too...
dirs=`find -maxdepth 1 -type d | grep -v "^.$"`

for dir in $(echo $dirs); do
    pushd $dir
    if [ -d ".git" ]; then 
        saved_branch=$(git branch | cut -d' ' -f2)
        branches=$(git branch -a | awk '{if($1 ~ /remotes\/origin\//){if($1 !~ /HEAD/){print}}}' | cut -d/ -f3)
        for branch in $(echo $branches); do
            diffs=$(git status -s)
            if [ "$diffs" == "" ]; then
                echo "Pulling branch $branch of $dir..."
                git checkout $branch
                git pull
            else
                printf "\tWARN: Local changes detected in branch $branch of $dir. Stashing...\n"
                git stash save --include-untracked
                git checkout $branch
                git pull
                echo "Stashed local changes. Don't forget to run 'git stash apply' later."
                git stash list
            fi
        done
        git checkout $saved_branch
    elif [ -d ".svn" ]; then
        printf "\tWARN: skipping subversion repo [$dir].\n"
    fi
    popd
done
