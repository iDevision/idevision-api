import asyncio
import builtins
import os
import inspect
import logging
import importlib
import time
import difflib
from types import ModuleType, FunctionType

from typing import List

import discord, twitchio, wavelink, aiohttp
from aiohttp import web

logger = logging.getLogger("site.rtfs")
logger.setLevel(10)

_builtins = [getattr(builtins, x) for x in dir(builtins)]

class Node:
    source = None
    file = None
    item = None
    parent = None
    module = None
    children = None

    def __init__(self, **kwargs):
        for a, b in kwargs.items():
            setattr(self, a, b)

        self.children = []

    def __str__(self):
        return f"<Node {self.item} with parent {self.parent} in module {self.module.__name__} file={self.file}>"

    __repr__ = __str__


class Index:
    def __init__(self, url, lib):
        self.lib = lib
        self.map = {}
        self.url = url
        self.map_keys = None

    async def index_module_layer(self, nodes: list, module):
        dirs = dir(module)
        for t in dirs:
            await asyncio.sleep(0)
            if t.startswith("__"):
                continue

            gets = getattr(module, t)

            if type(gets) != ModuleType and type(gets) not in (dict, list, int, str, bool):
                if type(gets) in _builtins and type(gets) is not type:
                    continue

                if type(gets) in (type(discord.opus.c_int16_ptr), type(discord.opus.EncoderStruct), type(None)):
                    continue

                if not isinstance(gets, type) and type(gets) != FunctionType:
                    gets = gets.__class__

                if gets.__module__ != module.__name__:
                    continue

                try:
                    nodes.append(Node(source=inspect.getsourcelines(gets), file=module.__file__, item=gets, module=module))
                except OSError:
                    pass

    async def index_class_layer(self, node: Node):
        children = dir(node.item)

        for child in children:
            await asyncio.sleep(0)
            if child.startswith('__'):
                continue

            gets = getattr(node.item, child)
            if isinstance(gets, property):
                gets = gets.fget

            try:
                node.children.append \
                    (Node(source=inspect.getsourcelines(gets), file=node.file, item=gets, module=node.module, parent=node))
            except OSError:
                # print("no source for ", gets)
                pass
            except TypeError:
                pass

    async def do_index(self, no, a, package=None):
        package = package or self.lib
        nodes = []
        base = os.path.dirname(package.__file__)

        logger.info(f"package:{package.__package__}: Indexing package ({no}/{a})")

        def _import_mod(r: str, f: str):
            r = r.replace(base, "").strip("\\")
            assert f.endswith(".py")
            modname = (r.replace("\\", ".").replace("/", ".") + "." if r else "") + f.replace(".py", "")
            modname = modname.strip().strip(".")
            if modname:
                modname = package.__package__.lower() + '.' + modname
            else:
                modname = package.__package__.lower()

            return importlib.import_module(modname)

        for root, dirs, files in os.walk(base):
            if root.endswith(("__pycache__", "bin")):
                continue

            for file in files:
                if file.endswith(".py") and not file.startswith("__"):
                    try:
                        mod = _import_mod(root, file)
                    except ModuleNotFoundError as e:
                        logger.warning(f"Failed {file}: {e.args[0]}")
                    else:
                        await self.index_module_layer(nodes, mod)

        for node in nodes:
            await self.index_class_layer(node)

        self.nodes = nodes
        logger.info(f"package:{package.__package__}: Created index. Mapping.")
        self.create_map()
        self.map_keys = list(self.map.keys())
        logger.info(f"package:{package.__package__}: Created map. {len(self.map_keys)} nodes indexed")
        return self

    def create_map(self):
        for node in self.nodes:
            if node.children:
                for n in node.children:
                    self.map[node.item.__name__ + "." + n.item.__name__] = n

            self.map[node.item.__name__] = node

    def find_matches(self, word: str) -> List[Node]:
        vals = difflib.get_close_matches(word, self.map_keys, cutoff=0.55)
        return [self.map[v] for v in vals]

    async def do_rtfs(self, item: str, text: bool):
        start = time.perf_counter()
        nodes = self.find_matches(item)
        out = {}
        for node in nodes:
            if not text:
                resp = f"{self.url}{node.module.__name__.replace('.', '/')}.py#L{node.source[1]}-L{node.source[1] + len(node.source[0])}"
            else:
                resp = "".join(node.source[0]).strip()
            name = []
            _node = node.parent
            while _node:
                name.append(_node.item.__name__)
                _node = _node.parent

            name = ".".join(list(reversed(name)) + [node.item.__name__])

            out[name] = resp

        end = time.perf_counter()

        return web.json_response({
            "nodes": out,
            "query_time": str(end-start)
        })


class Indexes:
    __indexable = {
        "discord.py": Index(f"https://github.com/Rapptz/discord.py/blob/v{discord.__version__.strip('a')}/", discord),
        "twitchio": Index(f"https://github.com/TwitchIO/TwitchIO/blob/v{twitchio.__version__.strip('a')}/", twitchio),
        "wavelink": Index(f"https://github.com/PythonistaGuild/Wavelink/v{wavelink.__version__.strip('a')}/", wavelink),
        "aiohttp": Index(f"https://github.com/aio-libs/aiohttp/blob/v{aiohttp.__version__.strip('a')}/", aiohttp)
    }
    def __init__(self):
        self.index = {}
        self._is_indexed = False
        self._loop = asyncio.get_event_loop()
        self._loop.create_task(self._do_index())

    @property
    def indexed(self):
        return self._is_indexed

    @property
    def libs(self):
        return ", ".join(self.__indexable.keys())

    def get_query(self, lib: str, query: str, as_text: bool = False):
        if not self._is_indexed:
            raise RuntimeError("Indexing is not complete")

        if lib not in self.index:
            return None

        return self.index[lib].do_rtfs(query, as_text)

    async def _do_index(self, *_):
        logger.info("Start Index")
        amount = len(self.__indexable)
        for n, (name, index) in enumerate(self.__indexable.items()):
            self.index[name] = await index.do_index(n+1, amount)

        logger.info("Finish Index")
        self._is_indexed = True
