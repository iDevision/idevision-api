from . import cdn, authorizations

def setup(app):
    app.add_routes(cdn.router)
    app.add_routes(authorizations.router)