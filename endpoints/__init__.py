from . import internal, cdn, public, games

def setup(app):
    internal.setup(app)
    cdn.setup(app)
    public.setup(app)
    games.setup(app)
