import math
from typing import Tuple, Optional

from aiohttp import web
from discord.ext.commands import CooldownMapping, BucketType, Cooldown

class Bucket2(BucketType):
    def get_key(self, request: web.Request):
        return request.remote

class Mapping(CooldownMapping):
    def get_bucket(self, request, current=None):
        self._verify_cache_integrity(current)
        #if request.remote == "127.0.0.1":
        #    return None

        key = self._bucket_key(request)
        if key not in self._cache:
            bucket = self._cooldown.copy()
            self._cache[key] = bucket
        else:
            bucket = self._cache[key]

        return bucket

    def update_rate_limit(self, request, current=None) -> Tuple[Optional[float], Optional[Cooldown]]:
        bucket: Cooldown = self.get_bucket(request, current)
        if bucket:
            return bucket.update_rate_limit(current), bucket

        return None, None

class Ratelimiter:
    def __init__(self, rate: int, per: int, callback):
        self.rate = rate
        self.per = per
        self.cb = callback
        self.map = Mapping.from_cooldown(rate, per, Bucket2.default)
        self.autoban = Mapping.from_cooldown(rate*2, per, Bucket2.default)

    def __call__(self, request: web.Request):
        return self._wrap_call(request)

    async def _wrap_call(self, request: web.Request):
        async with request.app.db.acquire() as conn:
            resp, login, did_ban = await self.do_call(request, conn)
            if did_ban or resp.status != 403:
                await conn.execute(
                    "INSERT INTO logs VALUES ($1, (now() at time zone 'utc'), $2, $3, $4, $5)",
                    request.headers.get("X-Forwarded-For") or request.remote,
                    request.headers.get("User-Agent", "!!Not given!!"),
                    request.path,
                    login,
                    403 if did_ban else resp.status
                )
            return resp

    async def do_call(self, request: web.Request, conn):
        ip = request.headers.get("X-Forwarded-For") or request.remote
        data = await conn.fetchrow("SELECT reason, (SELECT username FROM auths WHERE auth_key = $2) AS login "
                                               "FROM bans WHERE ip = $1", ip, request.headers.get("Authorization"))
        if data is not None and data['reason']:
            return web.Response(status=403, reason=data['reason']), None, False

        bucket = d = None
        if data is None or not data['login']:
            ban, _ = self.autoban.update_rate_limit(request)
            if ban is not None:
                await conn.execute(
                    "INSERT INTO bans (ip, user_agent, reason) VALUES ($1, $2, 'Auto-ban from api spam') ON CONFLICT DO NOTHING;",
                    ip, request.headers.get("user-agent"))
                return web.Response(status=403, reason="Auto-ban from api spam"), None, True

            d, bucket = self.map.update_rate_limit(request)

        if d:
            response = web.Response(status=429, reason="Too Many Requests"), data['login'], False
        else:
            response = await self.cb(request)

        if bucket:
            headers = {
                "ratelimit-remaining": bucket.get_tokens(),
                "ratelimit-max": bucket.rate,
                "ratelimit-reset": round(bucket._window + bucket.per),
                "ratelimit-retry-after": math.ceil(bucket.get_retry_after())
            }
        else:
            headers = {
                "ratelimit-remaining": 1,
                "ratelimit-max": 1,
                "ratelimit-reset": 0,
                "ratelimit-retry-after": 0
            }
        response.headers.update({x: str(y) for x, y in headers.items()})
        return response, data['login'] if data else None, False

def ratelimit(rate: int, per: int):
    def wrapped(func):
        return Ratelimiter(rate, per, func)
    return wrapped