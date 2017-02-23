from ipaddress import IPv4Network

import functools

import container
import handle
from dock import client


class Net:
    def __init__(self, addr):
        self.reserved = set()
        self.net = IPv4Network(addr)

    def reserve(self, ip):
        self.reserved.add(ip)

    def free(self, ip):
        self.reserved.remove(ip)

    def get(self):
        return str(next(filter(lambda ip: str(ip) not in self.reserved, self.net.hosts())))


class IPVSNet:
    def __init__(self, network, ipvs_exec):
        self.ipvs_exec = ipvs_exec
        self.network = network
        self.subnet = Net(network.attrs['IPAM']['Config'][0]['Subnet'])
        self.services = {}
        self.containers = {}

        self.subnet.reserve(self.network.attrs['IPAM']['Config'][0]['Gateway'])

        for cont, ip in self.all_ips():
            self.subnet.reserve(ip)
            self.containers[cont] = ip

        @self.handler(('connect',))
        def connect(cont):
            self.containers[cont.id] = self.find_ip(cont)
            self.add_real_server(cont)

        @self.handler(('disconnect',))
        def disconnect(cont):
            self.remove(cont)

    def connected(self, cont):
        try:
            self.find_ip(cont)
            return True
        except KeyError:
            return False

    def connect(self, cont):
        print("Connecting {cont} to network {name}".format(cont=container.fmt(cont), name=self.network.name))

        self.network.connect(cont)
        ip = self.find_ip(cont)
        self.subnet.reserve(ip)
        self.containers[cont.id] = ip

    def find_ip(self, cont):
        self.network.reload()
        return self.network.attrs['Containers'][cont.id]['IPv4Address'].split('/')[0]

    def add_real_server(self, cont):
        if not container.exposes_ports(cont):
            return

        if not self.connected(cont):
            self.connect(cont)

        service_name, server = container.ns(cont)
        rip = self.containers[cont.id]

        if not service_name in self.services:
            vip = self.subnet.get()
            self.subnet.reserve(vip)
            print("Service {service} available at {vip}".format(service=service_name, vip=vip))
            self.services[service_name] = Service(self.ipvs_exec, vip)

        service = self.services[service_name]

        def server_exec(cmd):
            print(cont.exec_run(cmd))

        print("Adding {cont} to virtual server {vip}".format(cont=container.fmt(cont), vip=service.vip))
        for port, _ in container.exposed_ports(cont):
            if not service.available(port):
                service.create_vs(port)

            service.add_real(rip, port, server_exec)

    def all_ips(self):
        self.network.reload()
        for cont, attrs in self.network.attrs['Containers'].items():
            yield cont, attrs['IPv4Address'].split('/')[0]

    def remove(self, cont):
        service, _ = container.ns(cont)

        print("Removing {cont} from virtual server {vip}".format(cont=container.fmt(cont), vip=self.services[service].vip))

        ip = self.containers[cont.id]
        del self.containers[cont.id]

        self.subnet.free(ip)
        for port, _ in container.exposed_ports(cont):
            self.services[service].remove(ip, port)

    def handler(self, actions):
        def decorator(fn):
            @functools.wraps(fn)
            def wrapper(event):
                if event['Actor']['Attributes']['name'] == self.network.name:
                    cont = client.containers.get(event['Actor']['Attributes']['container'])
                    fn(cont)

            handle.handler('network', actions)(wrapper)
            return fn

        return decorator


class Service:
    def __init__(self, ipvs_exec, ip):
        self.vip = ip
        self.ipvs_exec = ipvs_exec
        self.virtual_servers = {}

        self.ipvs_exec("ip addr add {vip}/32 broadcast {vip} dev eth0 label eth0:{vip}".format(vip=self.vip))
        self.ipvs_exec("route add -host {vip} dev eth0:{vip}".format(vip=self.vip))

    def add_real(self, rip, port, real_server_exec):
        self.virtual_servers[port].append(rip)
        self.ipvs_exec("ipvsadm -a -t {vip}:{port} -r {rip} -g -w 1".format(vip=self.vip, port=port, rip=rip))
        real_server_exec("ip addr add {vip}/32 broadcast {vip} dev lo label lo:{vip}".format(vip=self.vip))
        real_server_exec("route add -host {vip} dev lo:{vip}".format(vip=self.vip))
        real_server_exec("ip link set dev lo arp off")

    def create_vs(self, port):
        self.virtual_servers[port] = []
        self.ipvs_exec("ipvsadm -A -t {vip}:{port} -s rr".format(vip=self.vip, port=port))

    def available(self, port):
        return port in self.virtual_servers

    def remove(self, rip, port):
        self.virtual_servers[port].remove(rip)
        self.ipvs_exec("ipvsadm -a -t {vip}:{port} -d {rip}".format(vip=self.vip, port=port, rip=rip))
