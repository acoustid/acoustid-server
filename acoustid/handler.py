from werkzeug.wrappers import Response


class Handler(object):

    @classmethod
    def create_from_server(cls, server):
        return cls()

    def handle(self, req):
        raise NotImplementedError(self.handle)

