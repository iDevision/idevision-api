import asyncpg
import aiohttp
import asyncio
import datetime
import json

with open("config.json") as f:
    conf = json.load(f)

async def main():
    async def _get(_num):
        async with session.get(f"https://xkcd.com/{f'/{_num}/' if _num else ''}info.0.json") as resp:
            if 300 > resp.status >= 200:
                return await resp.json()
            elif resp.status == 404:
                print(f"comic {_num} not found")
            else:
                print(f"Failing at {_num}")
                print(resp.status, resp.reason, resp.headers, await resp.text())
                resp.raise_for_status()

    def formatter(_data: dict):
        d = datetime.datetime(year=int(_data['year']), month=int(_data['month']), day=int(_data['month']), minute=0, hour=0, second=0)
        return [_data['num'], d, _data['safe_title'], _data['title'], _data['alt'], _data['transcript'] or None,
                _data['news'] or None, _data['img'], f"https://xkcd.com/{_data['num']}"]

    session = aiohttp.ClientSession(headers={"User-Agent": "Idevision.net indexer"})
    db = await asyncpg.connect(conf['db'])

    latest = await _get(None)
    top = latest['num']

    for i in range(405, top):
        print(f"run comic {i}")
        d = formatter(await _get(i))
        await db.execute("INSERT INTO xkcd VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)", *d)

asyncio.run(main())