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
        return self.do_call(request)

    async def do_call(self, request: web.Request):
        print(request.headers)
        data = await request.app.db.fetchrow("SELECT reason, (SELECT username FROM auths WHERE auth_key = $2) AS login "
                                               "FROM bans WHERE ip = $1", request.remote, request.headers.get("Authorization"))
        if data is not None and data['reason']:
            return web.Response(status=403, reason=data['reason'])

        bucket = d = None
        if data is None or not data['login']:
            ban, _ = self.autoban.update_rate_limit(request)
            if ban is not None:
                await request.app.db.execute(
                    "INSERT INTO bans (ip, user_agent, reason) VALUES ($1, $2, 'Auto-ban from api spam') ON CONFLICT DO NOTHING;",
                    request.remote, request.headers.get("user-agent"))
                return web.Response(status=403, reason="Auto-ban from api spam")

            d, bucket = self.map.update_rate_limit(request)

        if d:
            response = web.Response(status=429, reason="Too Many Requests")
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
        return response

def ratelimit(rate: int, per: int):
    def wrapped(func):
        return Ratelimiter(rate, per, func)
    return wrapped