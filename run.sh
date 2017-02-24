#!/usr/bin/env sh
echo docker run --privileged -v /var/run/docker.sock:/var/run/docker.sock -v /proc:/host-proc $@
docker run --privileged -v /var/run/docker.sock:/var/run/docker.sock -v /proc:/host-proc $@