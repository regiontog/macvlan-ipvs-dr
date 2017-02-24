import functools
from ipaddress import IPv4Network

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
        return str(next(filter(lambda ip: str(ip) not in self.reserved, reversed(list(self.net.hosts())))))


class IPVSNet:
    def __init__(self, network, ipvs_exec):
        self.ipvs_exec = ipvs_exec
        self.network = network
        self.subnet = Net(network.attrs['IPAM']['Config'][0]['Subnet'])
        self.services = {}
        self.containers = {}
        self.reals = {}

        self.subnet.reserve(self.network.attrs['IPAM']['Config'][0]['Gateway'])

        for cont, ip in self.all_ips():
            self.subnet.reserve(ip)
            self.containers[cont] = ip

        @self.handler(('connect',))
        def connect(cont):
            self.containers[cont.id] = self.find_ip(cont)
            self.subnet.reserve(self.containers[cont.id])
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
        self.containers[cont.id] = self.find_ip(cont)
        self.subnet.reserve(self.containers[cont.id])

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

        self.reals[rip] = RealServer(self.ipvs_exec, cont, rip)

        if not service_name in self.services:
            vip = self.subnet.get()
            self.subnet.reserve(vip)
            print("Service {service} available at {vip}".format(service=service_name, vip=vip))
            self.services[service_name] = Service(self.ipvs_exec, vip)

        service = self.services[service_name]

        print("Adding {cont} to virtual server {vip}".format(cont=container.fmt(cont), vip=service.vip))
        for port, _ in container.exposed_ports(cont):
            if not service.available(port):
                service.create_vs(port)

            service.add_real(self.reals[rip], port)

    def all_ips(self):
        self.network.reload()
        for cont, attrs in self.network.attrs['Containers'].items():
            yield cont, attrs['IPv4Address'].split('/')[0]

    def remove(self, cont):
        ip = self.containers[cont.id]

        if ip in self.reals:
            service, _ = container.ns(cont)
            print("Removing {cont} from virtual server {vip}".format(cont=container.fmt(cont),
                                                                     vip=self.services[service].vip))
            self.reals[ip].remove()
            del self.reals[ip]

        del self.containers[cont.id]
        self.subnet.free(ip)

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
    # TODO: Support udp, weights(heartbeat), and different scheduling-methods
    def __init__(self, ipvs_exec, ip):
        self.vip = ip
        self.ipvs_exec = ipvs_exec
        self.virtual_servers = {}
        self.lbl = ip.replace('.', '')

        self.ipvs_exec("ip addr add {vip}/32 broadcast {vip} dev eth0 label eth0:{lbl}".format(vip=self.vip, lbl=self.lbl))
        self.ipvs_exec("route add -host {vip} dev eth0:{lbl}".format(vip=self.vip, lbl=self.lbl))

    def add_real(self, real, port):
        self.virtual_servers[port].append(real.rip)
        self.ipvs_exec("ipvsadm -a -t {vip}:{port} -r {rip} -g -w 1".format(vip=self.vip, port=port, rip=real.rip))

        if not real.is_attached(self):
            real.attach(self)

    def create_vs(self, port):
        self.virtual_servers[port] = []
        self.ipvs_exec("ipvsadm -A -t {vip}:{port} -s rr".format(vip=self.vip, port=port))

    def destroy_vs(self, port):
        del self.virtual_servers[port]
        self.ipvs_exec("ipvsadm -D -t {vip}:{port}".format(vip=self.vip, port=port))

    def available(self, port):
        return port in self.virtual_servers

    def detach(self, real):
        destroy = []

        for port in self.virtual_servers:
            if real.rip in self.virtual_servers[port]:
                self.ipvs_exec("ipvsadm -d -t {vip}:{port} -r {rip}".format(vip=self.vip, port=port, rip=real.rip))
                self.virtual_servers[port].remove(real.rip)
                if len(self.virtual_servers[port]) <= 0:
                    destroy.append(port)

        for port in destroy:
            self.destroy_vs(port)



class RealServer:
    def __init__(self, ipvs_exec, cont, rip):
        self.pid = cont.attrs['State']['Pid']
        self.rip = rip
        self.ipvs_exec = ipvs_exec
        self.attached = set()
        self.container = cont

        self.ipvs_exec('mkdir -p /var/run/netns'.format(pid=self.pid))
        self.ipvs_exec('ln -s /host-proc/{pid}/ns/net /var/run/netns/{pid}'.format(pid=self.pid))
        self.ip_exec("ip link set dev lo arp off")

    def ip_exec(self, cmd):
        self.ipvs_exec('ip netns exec {pid} '.format(pid=self.pid) + cmd)

    def is_attached(self, service):
        return service in self.attached

    def attach(self, service):
        self.attached.add(service)
        self.ip_exec("ip addr add {vip}/32 broadcast {vip} dev lo label lo:{lbl}".format(vip=service.vip, lbl=service.lbl))
        self.ip_exec("route add -host {vip} dev lo:{lbl}".format(vip=service.vip, lbl=service.lbl))

    def remove(self):
        for service in self.attached:
            # self.ip_exec("ip route del {vip} dev lo:{lbl}".format(vip=service.vip, lbl=service.lbl))
            # self.ip_exec("ip addr del {vip} dev lo".format(vip=service.vip))
            service.detach(self)
