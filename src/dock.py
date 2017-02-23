import docker

client = docker.from_env()


def print_cmd(container, cmd):
    ret = container.exec_run(cmd)
    print(ret.decode('utf-8'), end='')