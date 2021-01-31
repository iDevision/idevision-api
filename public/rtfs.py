import os
import inspect
import importlib
import time
import difflib
from types import ModuleType, FunctionType

from typing import List

import discord
from aiohttp import web


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
    def __init__(self, url):
        self.map = {}
        self.url = url
        self.map_keys = None

    def index_module_layer(self, nodes: list, module):
        dirs = dir(module)
        for t in dirs:
            if t.startswith("__"):
                continue

            gets = getattr(module, t)

            if type(gets) != ModuleType and type(gets) not in (dict, list, int, str, bool):
                if type(gets) in globals()['__builtins__'].values() and type(gets) is not type:
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
                    # print("no source for ", gets)
                    pass

    def index_class_layer(self, node: Node):
        children = dir(node.item)

        for child in children:
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

    def do_index(self, package, no, a):
        print(f"[RTFS] Indexing package {package.__title__} ({no}/{a})")
        nodes = []
        base = os.path.dirname(package.__file__)
        def _import_mod(r: str, f: str):
            r = r.replace(base, "").strip("\\")
            assert f.endswith(".py")
            modname = (r.replace("\\", ".").replace("/", ".") + "." if r else "") + f.replace(".py", "")
            modname = modname.strip().strip(".")
            if modname:
                modname = package.__title__ + '.' + modname
            else:
                modname = package.__title__

            return importlib.import_module(modname)

        for root, dirs, files in os.walk(base):
            if root.endswith(("__pycache__", "bin")):
                continue

            for file in files:
                if file.endswith(".py") and not file.startswith("__"):
                    mod = _import_mod(root, file)
                    self.index_module_layer(nodes, mod)

        for node in nodes:
            self.index_class_layer(node)

        self.nodes = nodes
        print("[RTFS] Created index. Mapping.")
        self.create_map()
        self.map_keys = list(self.map.keys())
        print(f"[RTFS] Created map. {len(self.map_keys)} nodes indexed")
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

    async def do_rtfs(self, item):
        start = time.perf_counter()
        nodes = self.find_matches(item)
        out = {}
        for node in nodes:
            url = f"{self.url}{node.module.__name__.replace('.', '/')}.py#L{node.source[1]}-L{node.source[1] + len(node.source[0])}"
            name = []
            _node = node.parent
            while _node:
                name.append(_node.item.__name__)
                _node = _node.parent

            name = ".".join(list(reversed(name)) + [node.item.__name__])

            out[name] = url

        end = time.perf_counter()

        return web.json_response({
            "nodes": out,
            "query_time": str(end-start)
        })