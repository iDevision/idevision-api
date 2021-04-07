import aiohttp
import asyncio
import datetime
import time
import re
from aiohttp import web

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from utils import utils

# slight alterations to finder
def finder(text, collection, *, key=None):
    suggestions = []
    text = str(text)
    pat = '.*?'.join(map(re.escape, text))
    regex = re.compile(pat, flags=re.IGNORECASE)
    for item in collection:
        to_search = key(item) if key else item

        r = regex.search(to_search)
        if r:
            suggestions.append((len(r.group()), r.start(), item[1]))

    return [z for _, _, z in sorted(suggestions)]


class XKCD:
    def __init__(self, app):
        self.app = app
        self.app.loop.create_task(self.task())
        self._cache = {}

    def formatter(self, _data: dict):
        d = datetime.datetime(year=int(_data['year']), month=int(_data['month']), day=int(_data['month']), minute=0, hour=0,
                              second=0)
        return [_data['num'], d, _data['safe_title'], _data['title'], _data['alt'], _data['transcript'] or None,
                _data['news'] or None, _data['img'], f"https://xkcd.com/{_data['num']}"]

    async def task(self):
        self.session = aiohttp.ClientSession(headers={"user-agent": "Idevision.net XKCD index"})

        await asyncio.sleep(60*60*24)
        async with self.session.get("https://xkcd.com/info.0.json") as resp:
            data = await resp.json()
            data = self.formatter(data)
            v = await self.app.db.fetchrow("INSERT INTO xkcd VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) ON CONFLICT DO NOTHING RETURNING *;", *data)
            if v:
                self._cache[v['title']] = v['num']

    async def build(self, request: "utils.TypedRequest"):
        data = await request.conn.fetch("SELECT num, title FROM xkcd")
        for v in data:
            self._cache[v['title']] = v['num']
            for x in v['extra_tags']:
                self._cache[x] = v['num']


    async def search_xkcd(self, query: str, request: "utils.TypedRequest") -> web.Response:
        start = time.time()
        if not self._cache:
            await self.build(request)

        v = finder(query, list(self._cache.items()), key=lambda t: t[0])[:8]
        nodes = await request.conn.fetch(
            "SELECT "
            "num, posted, safe_title, title, alt, transcript, news, image_url, url "
            "FROM xkcd WHERE num = ANY($1)",
            v
        )
        end = time.time()
        r = []
        for x in nodes:
            d = dict(x)
            del d['extra_tags']
            d['posted'] = d['posted'].isoformat()
            r.append(d)

        return web.json_response({"nodes": r, "query_time": end-start})
