from .public import endpoints as public
from . import internal

def setup(app):
    app.add_routes(public.router)
    internal.setup(app)
