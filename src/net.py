from ipaddress import IPv4Network

import container


class Net:
    def __init__(self, addr):
        self.reserved = set()
        self.net = IPv4Network(addr)

    def reserve(self, ip):
        print("Reserving ip {ip}".format(ip=ip))
        self.reserved.add(ip)

    def get(self):
        return str(next(filter(lambda ip: str(ip) not in self.reserved, self.net.hosts())))

class IPVSNet:
    def __init__(self, network):
        self.network = network
        self.subnet = Net(network.attrs['IPAM']['Config'][0]['Subnet'])
        self.services = {}

        self.subnet.reserve(self.network.attrs['IPAM']['Config'][0]['Gateway'])

        for ip in self.all_ips():
            self.subnet.reserve(ip)

    def connected(self, cont):
        try:
            self.find_ip(cont)
            return True
        except KeyError:
            return False

    def connect(self, cont):
        print("Connecting {cont} to network {name}".format(cont=container.fmt(cont), name=self.network.name))

        self.network.connect(cont)
        self.subnet.reserve(self.find_ip(cont))

    def find_ip(self, cont):
        self.network.reload()
        return self.network.attrs['Containers'][cont.id]['IPv4Address'].split('/')[0]

    def add_real_server(self, cont):
        if not container.exposes_ports(cont):
            return

        if not self.connected(cont):
            self.connect(cont)

        service_name, server = container.ns(cont)
        rip = self.find_ip(cont)

        if not service_name in self.services:
            vip = self.subnet.get()
            self.subnet.reserve(vip)
            print("Service {service} available at {vip}".format(service=service_name, vip=vip))
            self.services[service_name] = Service(vip)

        service = self.services[service_name]

        print("Adding {cont} to virtual server {vip}".format(cont=container.fmt(cont), vip=service.vip))
        for port, _ in container.exposed_ports(cont):
            if not service.available(port):
                service.create_vs(port)

            service.add_real(rip, port, print)

    def all_ips(self):
        self.network.reload()
        for cont in self.network.attrs['Containers'].values():
            yield cont['IPv4Address'].split('/')[0]


class Service:
    def __init__(self, ip):
        self.vip = ip
        self.virtual_servers = {}

    def add_real(self, rip, port, real_server_exec):
        self.virtual_servers[port].append(rip)
        print("#TODO: ipvsadm -a -t {vip}:{port} -r {rip} -g -w 1".format(vip=self.vip, port=port, rip=rip))
        real_server_exec("ip addr add {vip}/32 dev lo".format(vip=self.vip))
        real_server_exec("ip link set dev lo arp off")

    def create_vs(self, port):
        print("Creating virtual server at {vip}:{port}".format(vip=self.vip, port=port))
        self.virtual_servers[port] = []
        print("#TODO: ipvsadm -A -t {vip}:{port}".format(vip=self.vip, port=port))

    def available(self, port):
        return port in self.virtual_servers
