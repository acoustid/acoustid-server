from acoustid.handler import Handler, Response


class IndexHandler(Handler):

    def handle(self, req):
        return Response('Hello world!')

