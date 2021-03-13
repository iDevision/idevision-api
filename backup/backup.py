import json
import aiofiles
from aiohttp import web

app = web.Application()
r = web.RouteTableDef()

@r.view("/{path:.*}")
async def catch_all_routes(_):
    try:
        async with aiofiles.open("./message.json") as f:
            data = json.loads(await f.read())
    except:
        return web.Response(status=503, reason="Service Unavailable",
                            text="The Idevision website is currently offline due to an unknown error.")
    else:
        try:
            return web.Response(
                status=data['status'],
                text=data['message']
            )
        except:
            return web.Response(status=503, reason="Service Unavailable",
                                text="The Idevision website is currently offline due to an unknown error.")

app.add_routes(r)

web.run_app(app, host="127.0.0.1", port=8349)