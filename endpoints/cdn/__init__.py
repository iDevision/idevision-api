from . import cdn

def setup(app):
    app.add_routes(cdn.router)