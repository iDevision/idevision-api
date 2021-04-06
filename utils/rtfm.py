import asyncio
import re
import io
import time
import zlib
import os
import datetime

import aiohttp
from aiohttp import web
from discord.ext import tasks

class InteralError(Exception):
    pass

class BadURL(Exception):
    pass

def finder(text, collection, labels=True, *, key=None, lazy=True):
    suggestions = []
    text = str(text)
    pat = '.*?'.join(map(re.escape, text))
    regex = re.compile(pat, flags=re.IGNORECASE)
    for item in collection:
        to_search = key(item) if key else item
        if not labels and item[1][1]:
            continue

        r = regex.search(to_search)
        if r:
            suggestions.append((len(r.group()), r.start(), item))

    def sort_key(tup):
        if key:
            return tup[0], tup[1], key(tup[2])
        return tup

    if lazy:
        return (z for _, _, z in sorted(suggestions, key=sort_key))
    else:
        return [z for _, _, z in sorted(suggestions, key=sort_key)]


class SphinxObjectFileReader:
    # Inspired by Sphinx's InventoryFileReader
    BUFSIZE = 16 * 1024

    def __init__(self, buffer):
        self.stream = io.BytesIO(buffer)

    def readline(self):
        return self.stream.readline().decode('utf-8')

    def skipline(self):
        self.stream.readline()

    def read_compressed_chunks(self):
        decompressor = zlib.decompressobj()
        while True:
            chunk = self.stream.read(self.BUFSIZE)
            if len(chunk) == 0:
                break
            yield decompressor.decompress(chunk)
        yield decompressor.flush()

    def read_compressed_lines(self):
        buf = b''
        for chunk in self.read_compressed_chunks():
            buf += chunk
            pos = buf.find(b'\n')
            while pos != -1:
                yield buf[:pos].decode('utf-8')
                buf = buf[pos + 1:]
                pos = buf.find(b'\n')


class DocReader:
    def __init__(self, app):
        self.usage = {}
        self._rtfm_cache = {}
        self.session = aiohttp.ClientSession(headers={"User-Agent": "Idevision.net Documentation Reader https://idevision.net/docs"})
        self.db = app.db
        app.loop.create_task(self.offload_unused_cache())

    async def offload_unused_cache(self):
        while True:
            await asyncio.sleep(600)
            await self.db.execute("DELETE FROM rtfm CASCADE WHERE expiry <= (now() at time zone 'utc')")

            now = datetime.datetime.utcnow()
            for key, i in self.usage.items():
                if (now - i).total_seconds() >= 1200 and key in self._rtfm_cache:
                    del self._rtfm_cache[key]

    def parse_object_inv(self, stream, url) -> dict:
        # key: (URL, label)
        result = {}

        # first line is version info
        inv_version = stream.readline().rstrip()

        if inv_version != '# Sphinx inventory version 2':
            raise RuntimeError('Invalid objects.inv file version.')

        # next line is "# Project: <name>"
        # then after that is "# Version: <version>"
        projname = stream.readline().rstrip()[11:]
        version = stream.readline().rstrip()[11:]

        # next line says if it's a zlib header
        line = stream.readline()
        if 'zlib' not in line:
            raise BadURL('Invalid objects.inv file, not z-lib compatible.')

        # This code mostly comes from the Sphinx repository.
        entry_regex = re.compile(r'(?x)(.+?)\s+(\S*:\S*)\s+(-?\d+)\s+(\S+)\s+(.*)')
        for line in stream.read_compressed_lines():
            match = entry_regex.match(line.rstrip())
            if not match:
                continue

            name, directive, prio, location, dispname = match.groups()
            domain, _, subdirective = directive.partition(':')
            if directive == 'py:module' and name in result:
                # From the Sphinx Repository:
                # due to a bug in 1.1 and below,
                # two inventory entries are created
                # for Python modules, and the first
                # one is correct
                continue

            # Most documentation pages have a label
            if directive == 'std:doc':
                subdirective = 'label'

            if location.endswith('$'):
                location = location[:-1] + name

            key = name if dispname == '-' else dispname
            if subdirective == "label":
                result[key] = os.path.join(url, location), True
            else:
                result[key] = os.path.join(url, location), False

        return result

    async def build_rtfm_lookup_table(self, request, url):
        exists = await request.conn.fetchrow("SELECT indexed FROM rtfm WHERE url = $1", url)
        if not exists:
            try:
                data, expires = await self.build_table_scheme(request, url)
                data = {
                    "index": data,
                    "indexed": datetime.datetime.utcnow(),
                    "expiry": expires
                }
            except InteralError as e:
                return web.Response(status=500, reason=e.args[0])
            except BadURL as e:
                return web.Response(status=400, reason=e.args[0])

        else:
            data = await request.conn.fetch("SELECT key, value, is_label FROM rtfm_lookup WHERE url = $1", url)
            data = {
                "index": {x['key']: (x['value'], x['is_label']) for x in data},
                "indexed": exists['indexed'],
                "expiry": exists["expiry"]
            }

        self._rtfm_cache[url] = data

    async def build_table_scheme(self, request, url):
        try:
            async with self.session.get(url + '/objects.inv') as resp:
                if resp.status != 200:
                    raise BadURL(f'No objects.inv found at {url}/objects.inv')

                stream = SphinxObjectFileReader(await resp.read())

        except aiohttp.TooManyRedirects:
            raise InteralError(f"Cannot fetch lookup table for {url}; we are being ratelimited. Try again later")

        data = self.parse_object_inv(stream, url)
        expires = await request.conn.fetchval("INSERT INTO rtfm VALUES ($1, ((now() AT TIME ZONE 'utc') + INTERVAL '1 week')) RETURNING expires", url)
        v = [(url, k, *v) for k, v in data.items()]
        await request.conn.executemany("INSERT INTO rtfm_lookup VALUES ($1, $2, $3, $4)", v)
        return data, expires

    async def do_rtfm(self, request, url, obj, labels=True, label_labels=False):
        start = time.perf_counter()

        self.usage[url] = datetime.datetime.utcnow()

        if url not in self._rtfm_cache:
            try:
                await self.build_rtfm_lookup_table(request, url)
            except RuntimeError as e:
                return web.Response(status=500, reason=e.args[0])

        cache = list(self._rtfm_cache[url]['index'].items())

        matches = finder(obj, cache, labels, key=lambda t: t[0], lazy=False)[:8]
        end = time.perf_counter()

        resp = {
            "nodes": {f"label:{key}" if label_labels and is_label else key: u for key, (u, is_label) in matches},
            "query_time": str(end-start),
            "_cache_indexed": self._rtfm_cache[url]['indexed'].isoformat(),
            "_cache_expires": self._rtfm_cache[url]['expiry'].isoformat()
        }
        return web.json_response(resp)
