from . import authorizations

def setup(app):
    app.add_routes(authorizations.router)