import asyncio
import aiohttp
from aiohttp import web
import launcher

launcher.test = True
loop = asyncio.get_event_loop()

async def try_route(session, route, method, payload):
    if payload:
        resp: aiohttp.ClientResponse = await session.request(url=route, method=method, json=payload)
    else:
        resp = await session.request(url=route, method=method)

    if 300 > resp.status >= 200:
        if resp.content_type == "application/json":
            data = await resp.json()
        else:
            data = ""
        state = "PASS"

    else:
        state = "FAIL"
        try:
            data = await resp.text()
        except:
            data = ""

    print(f"{method} :: {route} :: {state} :: {resp.status} :: {data}")

async def run_routes():
    await asyncio.sleep(1)
    session = aiohttp.ClientSession()
    base = "http://127.0.0.1:8333/api/"
    routes = {
        base + "media/images/abc.png": ("GET", None),
        base + "media/purge": ("DELETE", {"username": "iamtomahawkx"}),
        base + "media/stats": ("GET", None),
        base + "media/list": ("GET", None),
        base + "media/list/user/iamtomahawk": ("GET", None),
        base + "media/stats/user": ("GET", {"username": "iamtomahawkx"}),
        base + "users/manage": ("POST", {"username": "aaa", "authorization": "user.aaa.1234", "routes": ["*"]}),
        base + "users/manage": ("DELETE", {"username": "aaa"}),
        base + "users/deauth": ("POST", {"username": "aaa"}),
        base + "users/auth": ("POST", {"username": "aaa"}),
        base + "bots/stats": ("GET", None)
    }
    for route, data in routes.items():
        await try_route(session, route, *data)

    await session.close()


loop.create_task(web._run_app(launcher.app, host="127.0.0.1", port=8333))
loop.run_until_complete(run_routes())