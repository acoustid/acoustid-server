from acoustid.script import ScriptContext


class Handler(object):

    def __init__(self, ctx):
        # type: (ScriptContext) -> None
        self.ctx = ctx

    def handle(self, req):
        raise NotImplementedError(self.handle)
