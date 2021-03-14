from . import cdn, nodes

def setup(app):
    app.add_routes(cdn.router)
    nodes.setup(app)