import json
import pathlib
import aiofiles
from aiohttp import web

class App(web.Application):
    def __init__(self):
        with open("../config.json") as f:
            self.config = json.load(f)

        super(App, self).__init__()

        p = pathlib.Path("defaults.json")
        if p.exists():
            with p.open() as f:
                with open("message.json", "w") as msg:
                    msg.write(f.read())
app = App()
r = web.RouteTableDef()

@r.post("/_api/message")
async def update_message(request: web.Request):
    if "Authorization" not in request.headers:
        return web.Response(status=401)

    if request.headers.get("Authorization") != app.config['slave_key']:
        return web.Response(status=401)

    data = await request.json()
    with open("./message.json") as f:
        json.dump({
            "message": data['message'],
            "status": data['status']
        }, f)

    return web.Response(status=204)

@r.delete("/_api/message")
async def reset_message(request: web.Request):
    if "Authorization" not in request.headers:
        return web.Response(status=401)

    if request.headers.get("Authorization") != app.config['slave_key']:
        return web.Response(status=401)

    p = pathlib.Path("defaults.json")
    if p.exists():
        with p.open() as f:
            with open("message.json", "w") as msg:
                msg.write(f.read())
    else:
        with open("message.json", "w") as msg:
            json.dump({
                "message": "The Idevision website is currently offline due to an unknown error.",
                "status": 503
            }, msg)

    return web.Response(status=204)

@r.view("/{path:.*}")
async def catch_all_routes(_):
    try:
        async with aiofiles.open("./message.json") as f:
            data = json.loads(await f.read())
    except:
        return web.Response(status=503, reason="Service Unavailable",
                            text="The Idevision website is currently offline due to an unknown error. (FNF)")
    else:
        try:
            return web.Response(
                status=data['status'],
                text=data['message']
            )
        except:
            return web.Response(status=503, reason="Service Unavailable",
                                text="The Idevision website is currently offline due to an unknown error. (KE)")

app.add_routes(r)

web.run_app(app, host="127.0.0.1", port=8349)