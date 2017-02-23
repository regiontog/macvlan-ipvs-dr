#!/usr/bin/env python3

import json
import sys

from dock import client
from net import IPVSNet

handlers = []


def handle(event):
    for spec, fn in handlers:
        type, actions = spec
        if type == event['Type'] and event['Action'] in actions:
            fn(event)


def handler(type, actions):
    def decorator(fn):
        handlers.append(((type, actions), fn))
        return fn

    return decorator


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

    @handler('network', ('connect',))
    def connect(event):
        if event['Actor']['Attributes']['name'] == net.network.name:
            cont = client.containers.get(event['Actor']['Attributes']['container'])
            net.add_real_server(cont)

    self = client.containers.get(self_id)
    if not net.connected(self):
        net.connect(self)

    for container in net.network.containers:
        if container is not self:
            net.add_real_server(container)

    for event in client.events():
        handle(json.loads(event.decode('utf-8')))
