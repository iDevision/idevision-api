import ast
import asyncio
import difflib
import configparser
import os
import subprocess
import time
import logging
import re
from os import PathLike
from typing import Union, List, Dict

from aiohttp import web

logger = logging.getLogger("site.rtfs")
logger.setLevel(10)

class Node:
    file: str
    line: int
    end_line: int
    name: str
    url: str
    source: str

    def __init__(self, **kwargs):
        for a, b in kwargs.items():
            setattr(self, a, b)

    def __repr__(self):
        return f"<Node file={self.file} line={self.line} end_line={self.end_line} name={self.name} url={self.url}>"

def _get_attr_name(attr: ast.Attribute):
    if type(attr.value) is ast.Attribute:
        return _get_attr_name(attr.value)
class Index:
    def __init__(self, repo_path: str, index_folder: str, repo_url: str, branch: str=None, version=None):
        self.repo_path = repo_path
        if index_folder in ("", ".", "./"):
            self.index_folder = ""
        else:
            self.index_folder = index_folder

        self.repo_url = repo_url.strip("/")
        self.version = version

        if not os.path.exists(self.repo_path):
            subprocess.run(["git", "clone", self.repo_url, self.repo_path])

            if branch:
                subprocess.run(["/bin/bash", "-c", f"cd {self.repo_path} && git checkout {branch}"])

        if not branch:
            if not os.path.exists(os.path.join(repo_path, ".git")):
                raise ValueError("not a git repo, no branch")

            with open(os.path.join(repo_path, ".git", "HEAD"), encoding="utf8") as f:
                v = f.read()
            try:
                branch = v.split("ref: refs/heads/")[1].strip()
            except:
                with open(os.path.join(repo_path, ".git", "config"), encoding="utf8") as f:
                    c = configparser.ConfigParser()
                    c.read_file(f)

                branch = c.get('remote "origin"', "fetch").split("/")[-1]

        self.branch = branch
        self.nodes: Dict[str, Node] = {}

    async def index_class_function(self, nodes: dict, cls: ast.ClassDef, src: List[str], fn: Union[ast.FunctionDef, ast.AsyncFunctionDef]):
        clsname = cls.name

        for b in fn.body:
            await asyncio.sleep(0)
            if type(b) is ast.Assign:
                t0 = b.targets[0]
                fn_args = [*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs] # got screwed over by posonly args
                if type(t0) is ast.Attribute and _get_attr_name(t0) == fn_args[0].arg:
                    name = clsname + "." + t0.attr
                    if name not in nodes:
                        n = Node(
                            file=None,
                            line=b.lineno,
                            end_line=b.end_lineno,
                            name=name,
                            source="\n".join(src[b.lineno-1:b.end_lineno])
                        )
                        nodes[name] = n

    async def index_class(self, nodes: dict, src: List[str], cls: ast.ClassDef):
        clsname = cls.name

        for b in cls.body:
            t = type(b)
            if t is ast.Assign and not b.targets[0].id.startswith("__"):
                name = clsname + "." + b.targets[0].id
                if name not in nodes:
                    n = Node(
                        file=None,
                        line=b.lineno,
                        end_line=b.end_lineno,
                        name=name,
                        source="\n".join(src[b.lineno-1:b.end_lineno])
                    )
                    nodes[name] = n

            elif t in (ast.FunctionDef, ast.AsyncFunctionDef):
                if not b.name.startswith("__"):
                    nodes[clsname + "." + b.name] = Node(
                        file=None,
                        line=b.lineno,
                        end_line=b.end_lineno,
                        name=clsname + "." + b.name,
                        source="\n".join(src[b.lineno-1:b.end_lineno])
                    )
                await self.index_class_function(nodes, cls, src, b)

    async def index_file(self, _nodes: dict, fp: Union[str, PathLike], dirs: List[str]):
        nodes = {}
        with open(fp, encoding="utf8") as f:
            src = f.read()

        lines = src.split("\n")
        node = ast.parse(src)

        for b in node.body:
            if type(b) is ast.ClassDef:
                nodes[b.name] = Node(
                    file=None,
                    line=b.lineno,
                    end_line=b.end_lineno,
                    name=b.name,
                    source="\n".join(lines[b.lineno-1:b.end_lineno])
                )
                await self.index_class(nodes, lines, b)

            elif type(b) is ast.Assign and isinstance(b.targets[0], ast.Name):
                name = b.targets[0].id
                if name not in nodes:
                    n = Node(
                        file=None,
                        line=b.lineno,
                        end_line=b.end_lineno,
                        name=name,
                        source="\n".join(lines[b.lineno-1:b.end_lineno])
                    )
                    nodes[name] = n

        pth = "/".join(dirs)
        for n in nodes.values():
            n.file = pth

        _nodes.update(nodes)

    async def index_directory(self, nodes: dict, idx_pth: str, parents: List[str], index_dir: str):
        parents = (parents and parents.copy()) or []
        target = os.path.join(idx_pth, *parents, index_dir)
        parents.append(index_dir)
        idx = os.listdir(target)

        for f in idx:
            if f == "types":
                continue

            if os.path.isdir(os.path.join(target, f)):
                await self.index_directory(nodes, idx_pth, parents, f)

            elif f.endswith(".py"):
                await self.index_file(nodes, os.path.join(target, f), parents+[f])

    async def index_lib(self):
        await self.index_directory(self.nodes, self.repo_path, [], self.index_folder)

        for name, n in self.nodes.items():
            n.url = f"{self.repo_url}/blob/{self.branch}/{n.file}#L{n.line}-L{n.end_line}"

        self.keys = list(self.nodes.keys())
        if not self.version and '__version__' in self.nodes:
            v = re.search("__version__\s*=\s*'|\"((\d|\.)*)'|\"", self.nodes['__version__'].source)
            if v:
                self.version = v.group(1)
            else:
                print(self.nodes['__version__'], self.nodes['__version__'].source)

    def find_matches(self, word: str) -> List[Node]:
        vals = difflib.get_close_matches(word, self.keys, cutoff=0.55)
        return [self.nodes[v] for v in vals]

class Indexes:
    __indexable = {
        "discord.py-2": Index("repos/discord.py-2", "discord", "https://github.com/Rapptz/discord.py/"),
        "discord.py": Index("repos/discord.py", "discord", "https://github.com/Rapptz/discord.py/"),
        "twitchio": Index("repos/TwitchIO", "twitchio", "https://github.com/TwitchIO/TwitchIO/"),
        "wavelink": Index("repos/Wavelink", "wavelink", "https://github.com/PythonistaGuild/Wavelink/"),
        "aiohttp": Index("repos/aiohttp", "aiohttp", "https://github.com/aio-libs/aiohttp/"),
        "enhanced-discord.py": Index("repos/enhanced-discord.py", "discord", "https://github.com/Idevision/Enhanced-discord.py", branch="2.0")
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

    @property
    def lib_index(self):
        return {
            x: y.version for x, y in self.__indexable.items()
        }

    def get_query(self, lib: str, query: str, as_text: bool = False):
        if not self._is_indexed:
            raise RuntimeError("Indexing is not complete")

        if lib not in self.index:
            return None

        start = time.monotonic()
        resp = self.index[lib].find_matches(query)
        end = time.monotonic() - start
        return web.json_response({
            "nodes": {x.name: (x.url if not as_text else x.source) for x in resp},
            "query_time": end
        })

    async def _do_index(self, *_):
        logger.info("Start Index")
        amount = len(self.__indexable)
        for n, (name, index) in enumerate(self.__indexable.items()):
            logger.info(f"Indexing module {name} ({n+1}/{amount})")
            self.index[name] = index
            await index.index_lib()
            logger.info(f"Finished indexing module {name} ({len(index.nodes)} nodes)")

        logger.info("Finish Index")
        self._is_indexed = True
