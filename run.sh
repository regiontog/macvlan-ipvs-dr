#!/usr/bin/env sh
echo docker run --privileged -v /var/run/docker.sock:/var/run/docker.sock $1 $2
docker run --privileged -v /var/run/docker.sock:/var/run/docker.sock $1 $2