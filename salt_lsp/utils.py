"""
Utility functions to extract data from the files
"""

import os
import os.path
import shlex
import subprocess
from typing import Iterator, List, Optional, TypeVar
from urllib.parse import urlparse

from pygls.lsp.types import Position, Range

import salt_lsp.parser as parser
from salt_lsp.parser import AstNode


def get_git_root(path: str) -> str:
    return str(
        subprocess.run(
            shlex.split("git rev-parse --show-toplevel"),
            cwd=os.path.dirname(path),
            check=True,
            capture_output=True,
        ).stdout,
        encoding="utf-8",
    )


def get_top(path: str) -> Optional[str]:
    parent = os.path.dirname(path)
    if not bool(parent):
        return None
    if os.path.isfile(os.path.join(parent, "top.sls")):
        return parent
    return get_top(parent)


def get_root(path: str) -> str:
    root = get_top(path)
    return root or get_git_root(path)


def get_sls_includes(path: str) -> List[str]:
    sls_files = []
    top = get_root(path)
    for root, _, files in os.walk(top):
        base = root[len(top) + 1 :].replace(os.path.sep, ".")
        sls_files += [
            base + (file[:-4] if file != "init.sls" else "")
            for file in files
            if file.endswith(".sls")
        ]
    return sls_files


def construct_path_to_position(
    document: str, pos: Position
) -> List[parser.AstNode]:
    tree = parser.parse(document)
    found_node = None
    parser_pos = parser.Position(line=pos.line, col=pos.character)

    def visitor(node: parser.AstNode) -> bool:
        if parser_pos >= node.start and parser_pos < node.end:
            nonlocal found_node
            found_node = node
        return True

    tree.visit(visitor)

    if not found_node:
        return []

    context: List[parser.AstNode] = []
    node: Optional[parser.AstNode] = found_node
    while node:
        context.insert(0, node)
        node = node.parent
    return context


def position_to_index(text, line, column):
    split = text.splitlines(keepends=True)
    return sum([len(l) for i, l in enumerate(split) if i < line]) + column


T = TypeVar("T")


def get_last_element_of_iterator(iterator: Iterator[T]) -> Optional[T]:
    """
    Returns the last element of from an iterator or None if the iterator is
    empty.
    """
    try:
        *_, last = iterator
        return last
    except ValueError:
        # empty iterator
        return None


class FileUri:
    """Simple class for handling file:// URIs"""

    def __init__(self, uri: str) -> None:
        self._parse_res = urlparse(uri)
        if self._parse_res.scheme != "" and self._parse_res.scheme != "file":
            raise ValueError(f"Invalid uri scheme {self._parse_res.scheme}")

    @property
    def path(self) -> str:
        return self._parse_res.path


def is_valid_file_uri(uri: str) -> bool:
    """Returns True if uri is a valid file:// URI"""
    try:
        FileUri(uri)
        return True
    except ValueError:
        return False


def ast_node_to_range(node: AstNode) -> Optional[Range]:
    """
    Converts a AstNode to a Range spanning from the node's starts to its end.

    If the node's start or end are None, then None is returned.
    """
    if node.start is None or node.end is None:
        return None
    return Range(start=node.start.to_lsp_pos(), end=node.end.to_lsp_pos())
