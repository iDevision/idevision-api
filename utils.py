import sys
import asyncio
import json
import pathlib
from typing import Callable, Optional

import asyncpg
from aiohttp import web

test = "--unittest" in sys.argv

async def get_authorization(request: "TypedRequest", authorization):
    if request.app.test:
        return "iamtomahawkx", ["*"]

    resp = await request.app.db.fetchrow("SELECT username, allowed_routes, administrator FROM auths WHERE auth_key = $1 and active = true", authorization)
    if resp is not None:
        return resp['username'], resp['allowed_routes'], resp['administrator']
    return None, []

def route_allowed(allowed_routes, route):
    if "*" in allowed_routes:
        return True

    if "{" in route:
        route = route.split("{")[0] # remove any args

    route = route.strip("/")
    return route in allowed_routes

class App(web.Application):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, middlewares=[shuttingdown_middleware])
        self._loop = asyncio.get_event_loop()
        self.last_upload = None
        self.on_startup.append(self.async_init)
        self.test = test
        self._closing = False

        p = pathlib.Path("config.json")
        if not p.exists():
            raise RuntimeError("The config.json file was not found, aborting master boot.")

        with p.open() as f:
            self.settings = json.load(f)

        self.slaves = {}

    @property # get rid of the deprecation warning
    def loop(self) -> asyncio.AbstractEventLoop:
        return self._loop

    async def async_init(self, _):
        if test:
            pass
        else:
            try:
                self.db: asyncpg.Pool = await asyncpg.create_pool(self.settings['db'])
            except:
                self.stop()
                raise RuntimeError("Failed to connect to the database")

            self._task = self._loop.create_task(self.offline_task())

        p = pathlib.Path("backup/defaults.json")
        if p.exists():
            with p.open() as f:
                with open("backup/message.json", "w") as msg:
                    msg.write(f.read())
        else:
            with open("backup/message.json", "w") as msg:
                json.dump({
                    "message": "The Idevision website is currently offline due to an unknown error.",
                    "status": 503
                }, msg)

    async def offline_task(self):
        while True:
            await asyncio.shield(self.db.execute("DELETE FROM bans WHERE expires is not null and expires <= (now() at time zone 'utc')"), loop=self._loop)
            await asyncio.sleep(120)

    def stop(self):
        self._closing = True
        async def _stop():
            await asyncio.sleep(3) # finish up pending requests
            try:
                self._task.cancel()
            except: pass
            self._loop.stop()

            with open("backup/message.json") as f:
                json.dump({
                    "message": "The service is currently restarting. Try again in 30 seconds.",
                    "status": 503
                }, f)

        self._loop.create_task(_stop())

@web.middleware
async def shuttingdown_middleware(request: "TypedRequest", handler: Callable):
    if request.app._closing:
        return web.Response(status=503, reason="Restarting", body="Service is restarting, please try again in 30 seconds.")

    return await handler(request)

class TypedRequest(web.Request):
    app: App
    username: Optional[str]