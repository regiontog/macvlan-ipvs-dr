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