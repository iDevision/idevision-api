from . import authorizations, permissions

def setup(app):
    app.add_routes(authorizations.router)
    app.add_routes(permissions.router)