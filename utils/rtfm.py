import asyncio
import re
import io
import time
import json
import zlib
import os
import datetime

from typing import Tuple, List

import aiohttp
from aiohttp import web

import utils


class InternalError(Exception):
    pass

class BadURL(Exception):
    pass

class ItsFuckingDead(InternalError):
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
        self.lock = asyncio.Lock()
        app.loop.create_task(self.offload_unused_cache())

    async def offload_unused_cache(self):
        while True:
            await asyncio.sleep(600)
            await self.db.execute("DELETE FROM rtfm CASCADE WHERE expiry <= (now() at time zone 'utc')")

            now = datetime.datetime.utcnow()
            async with self.lock:
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
        exists = await request.conn.fetchrow("SELECT indexed, expiry FROM rtfm WHERE url = $1", url)
        if not exists:
            try:
                data, expires = await self.build_table_scheme(request, url)
                data = {
                    "index": data,
                    "indexed": datetime.datetime.utcnow(),
                    "expiry": expires
                }
            except InternalError as e:
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
            raise InternalError(f"Cannot fetch lookup table for {url}; we are being ratelimited. Try again later")

        data = self.parse_object_inv(stream, url)
        expires = await request.conn.fetchval("INSERT INTO rtfm VALUES ($1, ((now() AT TIME ZONE 'utc') + INTERVAL '3 days')) RETURNING expiry", url)
        v = [(url, k, *v) for k, v in data.items()]
        await request.conn.executemany("INSERT INTO rtfm_lookup VALUES ($1, $2, $3, $4)", v)
        return data, expires

    async def do_rtfm(self, request, url, obj, labels=True, label_labels=False):
        start = time.perf_counter()

        self.usage[url] = datetime.datetime.utcnow()

        if url not in self._rtfm_cache:
            async with self.lock:
                try:
                    await self.build_rtfm_lookup_table(request, url)
                except RuntimeError as e:
                    return web.Response(status=500, reason=e.args[0])

        try:
            cache = list(self._rtfm_cache[url]['index'].items())
        except KeyError:
            async with self.lock:
                try:
                    await self.build_rtfm_lookup_table(request, url)
                except RuntimeError as e:
                    return web.Response(status=500, reason=e.args[0])

            try:
                cache = list(self._rtfm_cache[url]['index'].items())
            except KeyError:
                raise RuntimeError("Cache pull fallback failed")

        matches = finder(obj, cache, labels, key=lambda t: t[0], lazy=False)[:8]
        end = time.perf_counter()

        resp = {
            "nodes": {f"label:{key}" if label_labels and is_label else key: u for key, (u, is_label) in matches},
            "query_time": str(end-start),
            "_cache_indexed": self._rtfm_cache[url]['indexed'].isoformat(),
            "_cache_expires": self._rtfm_cache[url]['expiry'].isoformat()
        }
        return web.json_response(resp)



def rs_finder(text, collection, *, key=None, lazy=True):
    suggestions = []
    text = str(text)
    pat = '.*?'.join(map(re.escape, text))
    regex = re.compile(pat, flags=re.IGNORECASE)
    for item in collection:
        if len(suggestions) >= 8:
            break

        to_search = key(item) if key else item

        r = regex.search(to_search)
        if r:
            suggestions.append((len(r.group()), r.start(), item))

    if lazy:
        return (z for _, _, z in suggestions)
    else:
        return [z for _, _, z in suggestions]


class CargoReader:
    JSSEARCH = re.compile(r"data-search-index-js=\"([^\"]*)\"|<script defer=\"\" src=\"([^\"]*)\"></script>")
    VERSIONSEARCH = re.compile(r"https://docs.rs/[^/]*/([\d|.]*)/[^/]*/")
    INDEXSEARCH = re.compile(r"'(.*[^\\])'")
    ITEM_TYPES = [
        "mod",
        "externcrate",
        "import",
        "struct",
        "enum",
        "fn",
        "type",
        "static",
        "trait",
        "impl",
        "tymethod",
        "method",
        "structfield",
        "variant",
        "macro",
        "primitive",
        "associatedtype",
        "constant",
        "associatedconstant",
        "union",
        "foreigntype",
        "keyword",
        "existential",
        "attr",
        "derive",
        "traitalias"
    ]
    __slots__ = "app", "session", "cache"

    def __init__(self, app):
        self.app = app
        self.session = None
        self.cache = {}

    async def _ainit(self):
        if not self.session:
            self.session = aiohttp.ClientSession(headers={"User-Agent": "Idevision doc reader"})

    async def do_rtfm(self, request, crate: str, query: str) -> web.Response:
        start = time.monotonic()
        data = await self.search(crate, query)
        end = time.monotonic() - start
        return web.json_response({
            "nodes": {t: x for (t, x) in data},
            "query_time": end
        })

    async def search_crate(self, crate: str, search: str) -> List[str]:
        return rs_finder(search, self.cache[crate], lazy=False, key=lambda m: m[0])[0:8]

    async def search(self, crate: str, search: str):
        if crate in self.cache:
            return await self.search_crate(crate, search)

        await self.index_crate(crate)
        return await self.search_crate(crate, search)

    async def index_crate(self, crate):
        data, baseurl = await self.get_crate(crate)
        await self.build_index(crate, data, baseurl)

    async def get_crate(self, crate: str) -> Tuple[dict, str]:
        await self._ainit()
        async with self.session.get(f"https://docs.rs/{crate}") as data:
            ver = self.VERSIONSEARCH.search(str(data.url)).groups()[0] if crate != "std" else "stable"
            try:
                pth = self.JSSEARCH.search(await data.text()).groups()
                pth = (pth[0] or pth[1]).replace("../", "")
            except:
                raise ItsFuckingDead()

        if crate == "std":
            loc = f"https://doc.rust-lang.org/stable/"
        else:
            loc = f"https://docs.rs/{crate}/{ver}/"

        async with self.session.get(loc+pth) as data:
            jsondata = json.loads(self.INDEXSEARCH.search((await data.text()).replace("\\\n", "").replace("\\'", "'")).groups()[0])

        return jsondata, loc

    async def build_index(self, _crate: str, jsondata: dict, baseurl: str):
        searchwords = []
        searchindex = []
        id = 0
        current_index = 0

        for crate, jsd in jsondata.items():
            crate_size = 0
            searchwords.append(crate)
            searchindex.append({
                "crate": crate,
                "ty": 1,
                "name": crate,
                "path": "",
                "desc": jsd['doc'],
                "parent": None,
                "type": None,
                "id": id,
                "normalized_name": crate.replace("_", "")
            })
            id += 1
            current_index += 1
            item_types = jsd['t']
            item_names = jsd['n']
            item_paths = jsd['q']
            item_descs = jsd['d']
            item_parent_indx = jsd['i']
            item_func_search_types = jsd['f']
            paths = jsd['p']
            last_path = ""

            for n, x in enumerate(paths):
                paths[n] = {"ty": x[0], "name": x[1]}

            ln = len(item_types)
            i = 0
            while i < ln:
                await asyncio.sleep(0)
                x = item_names[i]
                if isinstance(x, str):
                    word = x.lower()
                    searchwords.append(word)
                else:
                    word = ""
                    searchwords.append("")

                normalizedname = word.replace("_", "")
                row = {
                    "crate": crate,
                    "ty": item_types[i],
                    "name": x,
                    "path": item_paths[i] if item_paths[i] else last_path,
                    "desc": item_descs[i],
                    "parent": paths[item_parent_indx[i] - 1] if item_parent_indx[i] else None,
                    "type": item_func_search_types[i],
                    "id": id,
                    "normalized_name": normalizedname
                }
                id += 1
                searchindex.append(row)
                last_path = row['path']
                crate_size += 1
                i += 1

        self.cache[_crate] = ret = sorted([await self.build_href_and_path(x, baseurl) for x in searchindex], key=lambda m: m[0])
        return ret

    async def build_href_and_path(self, item: dict, root_path: str) -> Tuple[str, str]:
        type = self.ITEM_TYPES[item["ty"]]
        name = item['name']
        path = item['path']

        if type == "mod":
            display_path = path + "::"
            href = root_path + path.replace("::", "/") + "/" + name + "/index.html"
        elif type == "primitive" or type == "keyword":
            display_path = ""
            href = root_path + path.replace("::", "/") + "/" + type + "." + name + ".html"
        elif type == "externcrate":
            display_path = ""
            href = root_path + name + "/index.html"
        elif item['parent'] is not None:
            myparent = item['parent']
            anchor = "#" + type + "." + name
            parent_type = self.ITEM_TYPES[myparent['ty']]
            page_type = parent_type
            page_name = myparent['name']
            if parent_type == "primitive":
                display_path = myparent['name'] + "::" + name

            elif type == "structfield" and parent_type == "variant":
                enum_name_idx = item['path'].rfind("::")
                enum_name = item['path'][enum_name_idx + 2:]
                path = item['path'][0:enum_name_idx]
                display_path = path + "::" + enum_name + "::" + myparent['name'] + "::" + name
                anchor = "#variant." + myparent['name'] + ".field." + name
                page_type = "enum"
                page_name = enum_name

            else:
                display_path = path + "::" + myparent['name'] + "::" + name

            href = root_path + path.replace("::", "/") + "/" + page_type + "." + page_name + ".html" + anchor

        else:
            display_path = item['path'] + "::" + name
            href = root_path + item['path'].replace("::", "/") + "/" + type + "." + name + ".html"

        return display_path, href