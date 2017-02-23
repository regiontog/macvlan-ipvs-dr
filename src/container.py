from src.dock import client


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

    return image_name, container.name


def find_ip(container):
    return None


def exposed_ports(container):
    return None