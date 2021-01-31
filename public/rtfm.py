import re
import io
import time
import zlib
import datetime
import os

import aiohttp
from aiohttp import web
from discord.ext import tasks

def finder(text, collection, labels=True, *, key=None, lazy=True):
    suggestions = []
    text = str(text)
    pat = '.*?'.join(map(re.escape, text))
    regex = re.compile(pat, flags=re.IGNORECASE)
    for item in collection:
        to_search = key(item) if key else item
        if not labels and to_search.startswith("label:"):
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
    def __init__(self):
        self.usage = {}
        self._rtfm_cache = {}
        self.session = aiohttp.ClientSession(headers={"User-Agent": "Idevision.net Documentation Reader https://idevision.net/docs"})
        self.offload_unused_cache.start()

    def cog_unload(self):
        self.offload_unused_cache.cancel()

    @tasks.loop(minutes=1)
    async def offload_unused_cache(self):
        now = datetime.datetime.utcnow()
        for key, i in self.usage.items():
            if (now-i).total_seconds() >= 1200 and key in self._rtfm_cache:
                del self._rtfm_cache[key]

    def parse_object_inv(self, stream, url):
        # key: URL
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
            raise RuntimeError('Invalid objects.inv file, not z-lib compatible.')

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
                key = "label:"+key

            result[key] = os.path.join(url, location)

        return result

    async def build_rtfm_lookup_table(self, url):

        cache = {}

        async with self.session.get(url + '/objects.inv') as resp:
            if resp.status != 200:
                raise RuntimeError(f'Cannot build rtfm lookup table, try again later. (no objects.inv found at {url}/objects.inv)')

            stream = SphinxObjectFileReader(await resp.read())
            cache[url] = self.parse_object_inv(stream, url)

        if self._rtfm_cache is None:
            self._rtfm_cache = cache
        else:
            self._rtfm_cache.update(cache)

    async def do_rtfm(self, key, obj, labels=True, label_labels=False):
        if obj is None:
            return web.Response(status=400, reason="No search query provided")

        start = time.perf_counter()
        self.usage[key] = datetime.datetime.utcnow()

        if key not in self._rtfm_cache:
            try:
                await self.build_rtfm_lookup_table(key)
            except RuntimeError as e:
                return web.Response(status=500, reason=e.args[0])

        cache = list(self._rtfm_cache[key].items())

        matches = finder(obj, cache, labels, key=lambda t: t[0], lazy=False)[:8]

        end = time.perf_counter()

        resp = {
            "nodes": {key.replace("label:", "") if not label_labels else key: url for key, url in matches},
            "query_time": str(end-start)
        }
        return web.json_response(resp)
