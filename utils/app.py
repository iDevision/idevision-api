import sys
import asyncio
import json
import pathlib
from typing import Callable, Optional, Tuple, Dict

import asyncpg
from aiohttp import web

from utils.rtfs import Indexes
from utils.rtfm import DocReader, CargoReader
from utils.xkcd import XKCD

test = "--unittest" in sys.argv

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
        self.route_permissions: Dict[Tuple[str, str], str] = {}

    @property # get rid of the deprecation warning
    def loop(self) -> asyncio.AbstractEventLoop:
        return self._loop

    async def async_init(self, _):
        try:
            self.db: asyncpg.Pool = await asyncpg.create_pool(self.settings['db'], max_inactive_connection_lifetime=5)
        except Exception as e:
            self.stop()
            raise RuntimeError("Failed to connect to the database") from e

        async with self.db.acquire() as conn:
            await conn.execute(
                "INSERT INTO auths VALUES ('_internal', null, '{administrator}', true, null, true) ON CONFLICT DO NOTHING"
            )
            data = await conn.fetch(
                "SELECT route, method, permission from routes"
            )
            for record in data:
                self.route_permissions[(record['route'], record['method'])] = record['permission']

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

        self.rtfs = Indexes()
        self.rtfm = DocReader(self)
        self.xkcd = XKCD(self)
        self.cargo_rtfm = CargoReader(self)

    async def offline_task(self):
        while True:
            await asyncio.shield(self.db.execute("DELETE FROM bans WHERE expires is not null and expires <= (now() at time zone 'utc')"), loop=self._loop)
            await asyncio.sleep(120)

    def stop(self):
        self._closing = True
        p = pathlib.Path("backup/message.json")
        with p.open("w") as f:
            json.dump({
                "message": "Server Restarting",
                "status": 503
            }, f)

        async def _stop():
            try:
                self._task.cancel()
            except: pass
            await asyncio.sleep(3) # finish up pending requests
            self._loop.stop()

        self._loop.create_task(_stop())

@web.middleware
async def shuttingdown_middleware(request: "TypedRequest", handler: Callable):
    if request.app._closing:
        return web.Response(status=503, reason="Restarting", body="Service is restarting, please try again in 30 seconds.")

    return await handler(request)

class TypedRequest(web.Request):
    app: App
    user: Optional[dict]
    username: Optional[str]
    conn: asyncpg.Connection