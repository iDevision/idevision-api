import sys
import datetime
import asyncio
from typing import Callable

import prometheus_client
import asyncpg
from aiohttp import web

test = "--unittest" in sys.argv

async def get_authorization(request: "TypedRequest", authorization):
    if request.app.test:
        return "iamtomahawkx", ["*"]

    resp = await request.app.db.fetchrow("SELECT username, allowed_routes FROM auths WHERE auth_key = $1 and active = true", authorization)
    if resp is not None:
        return resp['username'], resp['allowed_routes']
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
        super().__init__(*args, **kwargs, middlewares=[self.shuttingdown_middleware])
        self.last_upload = None
        self.prometheus = {
            "counts": prometheus_client.Gauge("bot_data", "Guilds that the bot has", labelnames=["count", "bot"]),
            "websocket_events": prometheus_client.Counter("bot_events", "bot's metrics", labelnames=['event', "bot"]),
            "latency": prometheus_client.Gauge("bot_latency", "bot's latency", labelnames=["count", "bot"]),
            "ram_usage": prometheus_client.Gauge("bot_ram", "How much ram the bot is using", labelnames=["count", "bot"]),
            "online": prometheus_client.Info("bot_online", "the bot's status", labelnames=["bot"]),
        }
        self.bot_stats = {}
        self.on_startup.append(self.async_init)
        self._task = self._loop.create_task(self.offline_task())
        self.test = test
        self._closing = False

    @property # get rid of the deprecation warning
    def loop(self) -> asyncio.AbstractEventLoop:
        return self._loop

    async def async_init(self, _):
        if test:
            pass
        else:
            self.db: asyncpg.Pool = await asyncpg.create_pool("postgresql://tom:tom@127.0.0.1:5432/idevision")

    async def shuttingdown_middleware(self, request: "TypedRequest", handler: Callable):
        if self._closing:
            return web.Response(status=503, reason="Restarting", body="Service is restarting, please try again in 30 seconds.")

        return await handler(request)

    async def offline_task(self):
        while True:
            for bname, bot in self.bot_stats.items():
                if bot['last_post'] is None or (datetime.datetime.utcnow() - bot['last_post']).total_seconds() > 120:
                    self.prometheus['online'].labels(bot=bname).info({"state": "Offline"})

            await asyncio.shield(self.db.execute("DELETE FROM bans WHERE expires is not null and expiry <= (now() at time zone 'utc')"), loop=self._loop)
            await asyncio.sleep(120)

    def stop(self):
        self._closing = True
        async def _stop():
            await asyncio.sleep(3) # finish up pending requests
            self._task.cancel()
            self._loop.stop()

        self._loop.create_task(_stop())

class TypedRequest(web.Request):
    app: App