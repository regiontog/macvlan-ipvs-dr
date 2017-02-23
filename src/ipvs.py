#!/usr/bin/env python3

import json
import sys

import handle
from dock import client
from net import IPVSNet

if __name__ == '__main__':
    if len(sys.argv) <= 1:
        print('Not enough arguments')
        sys.exit(-1)
    elif len(sys.argv) <= 2:
        import socket

        network_name = sys.argv[1]
        self_id = socket.gethostname()
    else:
        network_name = sys.argv[1]
        self_id = sys.argv[2]

    def ipvs_exec(cmd):
        print(self.exec_run(cmd))

    net = IPVSNet(client.networks.get(network_name), ipvs_exec)

    self = client.containers.get(self_id)
    if not net.connected(self):
        net.connect(self)

    for container in net.network.containers:
        if container is not self:
            net.add_real_server(container)

    for event in client.events():
        handle.handle(json.loads(event.decode('utf-8')))
