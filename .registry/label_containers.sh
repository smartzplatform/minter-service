#!/bin/bash

if [ "$TRAVIS" == "true" ];
then
	LABELS="LABEL git.branch=\"$TRAVIS_BRANCH\"\n"
	LABELS+="LABEL git.commit=\"$(git log -1  --pretty=format:'%H')\"\n"
	LABELS+="LABEL git.commit.short=\"$(git log -1  --pretty=format:'%h')\"\n"
	LABELS+="LABEL git.commit.message=\"$(git log -1  --pretty=format:'%B')\"\n"
	LABELS+="LABEL git.committer=\"$(git log -1 --pretty=format:'%cn <%ce>')\"\n"
	LABELS+="LABEL git.date=\"$(git log -1  --pretty=format:'%cd')\"\n"
	LABELS+="LABEL git.timestampt=\"$(git log -1  --pretty=format:'%ct')\"\n"
	LABELS+="LABEL ci=\"Travis CI\"\n"
	LABELS+="LABEL ci.travis_build_number=\"$TRAVIS_BUILD_NUMBER\"\n"
	LABELS+="LABEL ci.build_date=$(date -u +\"%Y-%m-%dT%H:%M:%SZ\")\n"
	echo -e "$LABELS"
	for dockerfile in `find "${TRAVIS_BUILD_DIR}" -name Dockerfile`;
        do
            echo "Write labels to $dockerfile"
            echo -e "${LABELS}" >> $dockerfile
        done
fi
