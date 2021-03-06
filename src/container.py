from dock import client


def fmt(container):
    image, name = ns(container)
    return '[{image}/{name}]'.format(image=image, name=name)


def ns(container):
    image_name = container.attrs['Image']

    image = client.images.get(image_name)
    if len(image.tags) > 0:
        image_name = image.tags[0].split(":")[0]
    else:
        image_name = image.short_id.split(":")[1]

    image_name.replace('/', '-')
    return image_name, container.name


def exposed_ports(container):
    ports = container.attrs['Config']['ExposedPorts'].keys()
    for port in ports:
        port, protocol = port.split('/')[0], port.split('/')[1]
        yield port, protocol


def exposes_ports(container):
    return 'ExposedPorts' in container.attrs['Config']