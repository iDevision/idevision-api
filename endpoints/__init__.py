from . import internal, cdn, public

def setup(app):
    internal.setup(app)
    cdn.setup(app)
    public.setup(app)
