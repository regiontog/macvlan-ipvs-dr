#!/usr/bin/env python3

import sys

from net import IPVSNet

from dock import client

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

    net = IPVSNet(client.networks.get(network_name))

    self = client.containers.get(self_id)
    print(self.name)
    # net.connect(self)

    for container in net.network.containers:
        if container is not self:
            net.add_real_server(container)

    for event in client.events():
        print(event)
