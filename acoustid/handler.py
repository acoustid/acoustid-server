from werkzeug.wrappers import Request, Response
from acoustid.script import ScriptContext


class Handler(object):

    def __init__(self, ctx):
        # type: (ScriptContext) -> None
        self.ctx = ctx

    def handle(self, req):
        # type: (Request) -> Response
        raise NotImplementedError(self.handle)
