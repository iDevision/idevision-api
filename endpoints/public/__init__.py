from . import homepage, endpoints

def setup(app):
    homepage.setup(app)
    app.add_routes(endpoints.router)