from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from os.path import abspath, dirname, exists, isdir, join
from typing import Any, Callable, List, Optional, Sequence, cast

import yaml
from jinja2 import Undefined
from lsprotocol import types


class NullUndefined(Undefined):
    def __getattr__(self, key):
        return ""


@dataclass
class Position:
    """
    Describes a position in the document
    """

    line: int
    col: int

    def __lt__(self, other):
        if not isinstance(other, Position):
            return NotImplemented
        return (
            self.line < other.line or self.line == other.line and self.col < other.col
        )

    def __gt__(self, other):
        if not isinstance(other, Position):
            return NotImplemented
        return (
            self.line > other.line or self.line == other.line and self.col > other.col
        )

    def __le__(self, other):
        return self < other or self == other

    def __ge__(self, other):
        return self > other or self == other

    def to_lsp_pos(self) -> types.Position:
        """Convert this position to pygls' native Position type."""
        # TODO ? numbers are starting from 0 for line and column maybe we need to
        # offset by 1
        return types.Position(line=self.line, character=self.col)

    def __repr__(self) -> str:
        return f"Position(line={self.line + 1}, col={self.col + 1})"


@dataclass
class AstNode(ABC):
    """
    Base class for all nodes of the Abstract Syntax Tree
    """

    start: Optional[Position] = None
    end: Optional[Position] = None
    parent: Optional["AstNode"] = field(compare=False, default=None, repr=False)
    id: Optional[str] = None

    def get_symbol(self) -> str:
        return "?"

    def visit(self: "AstNode", visitor: Callable[["AstNode"], bool]) -> None:
        """
        Apply a visitor function to the node and apply it on children if the
        function returns True.
        """
        visitor(self)

    def get_id(self) -> Optional[str]:
        return None

    def as_string(self, indentation: int = 0) -> List[str]:
        prefix = ""
        if indentation > 0:
            prefix = "|_"

        v = self.get_id()
        if v is not None:
            v = f" {v} "
        else:
            v = ""
        start_line = self.start.line + 1 if self.start else "None"
        start_col = self.start.col + 1 if self.start else "None"
        end_line = self.end.line + 1 if self.end else "None"
        end_col = self.end.col + 1 if self.end else "None"
        ret = [
            f"{' ' * (indentation-2)}{prefix}{self.get_symbol()}{v}"
            f"({start_line},{start_col}) <-> "
            f"({end_line},"
            f"{end_col})\n"
        ]
        return ret


class AstMapNode(AstNode, ABC):
    """
    Base class for all nodes that are mappings
    """

    @abstractmethod
    def add(self: "AstMapNode") -> AstNode:
        """
        Abstract function to add an item
        """
        raise NotImplementedError()

    @abstractmethod
    def get_children(self: "AstMapNode") -> Sequence[AstNode]:
        """
        Returns all the children nodes
        """
        raise NotImplementedError()

    def visit(self, visitor: Callable[[AstNode], bool]) -> None:
        """
        Apply a visitor function to the node and apply it on children if the
        function returns True.
        """
        if visitor(self):
            for child in self.get_children():
                child.visit(visitor)

    def as_string(self, indentation: int = 0) -> List[str]:
        ret = super().as_string(indentation)
        for s in self.get_children():
            ret.extend(s.as_string(indentation + 2))
        return ret


@dataclass
class IncludeNode(AstNode):
    """
    Represents an item in the includes node
    """

    value: Optional[str] = None

    def get_symbol(self) -> str:
        return "i"

    def get_id(self) -> Optional[str]:
        return self.value

    def get_file(self: "IncludeNode", top_path: str) -> Optional[str]:
        """
        Convert the dotted value of the include into a proper file path
        based on the path of the top of the states folder.

        :param top_path: the path to the top states folder
        """
        if self.value is None:
            return None

        top_path = (
            abs_top_path
            if isdir(abs_top_path := abspath(top_path))
            else dirname(abs_top_path)
        )

        dest = join(*self.value.split("."))
        init_sls_path = join(top_path, dest, "init.sls")
        entry_sls_path = join(top_path, f"{dest}.sls")
        if exists(init_sls_path):
            return init_sls_path
        if exists(entry_sls_path):
            return entry_sls_path
        return None


@dataclass
class IncludesNode(AstNode):
    """
    Node representing the list of includes
    """

    includes: List[IncludeNode] = field(default_factory=list)

    def get_symbol(self) -> str:
        return "I"

    def add(self: "IncludesNode") -> IncludeNode:
        """
        Add a child node and return it.
        """
        self.includes.append(IncludeNode())
        return self.includes[-1]


@dataclass
class StateParameterNode(AstNode):
    """
    Node representing a parameter of the state definition.
    """

    name: Optional[str] = None
    value: Any = None

    def get_symbol(self) -> str:
        return "P"

    def get_id(self) -> Optional[str]:
        return self.name

    def set_key(self: "StateParameterNode", key: str) -> AstNode:
        """
        Set the name of the parameter. If getting a requisites, tell the parent
        to handle it and return the newly created node.

        :return: the node that finally got the name
        """
        requisites_keys = [
            "require",
            "onchanges",
            "watch",
            "listen",
            "prereq",
            "onfail",
            "use",
        ]
        all_requisites_keys = (
            requisites_keys
            + [k + "_any" for k in requisites_keys]
            + [k + "_in" for k in requisites_keys]
        )
        if key in all_requisites_keys and isinstance(self.parent, StateCallNode):
            return self.parent.convert(self, key)
        self.name = key
        return self


@dataclass
class RequisiteNode(AstNode):
    """
    Node representing one requisite
    """

    module: Optional[str] = None
    reference: Optional[str] = None

    def get_symbol(self) -> str:
        return "r"

    def get_id(self) -> Optional[str]:
        return f"{self.module}-{self.reference}"

    def set_key(self: "RequisiteNode", key: str) -> AstNode:
        """
        Set the module of the requisite

        :param key: the module to set
        :return: the node that was updated
        """
        self.module = key
        return self


@dataclass
class RequisitesNode(AstMapNode):
    """
    Node Representing the list of requisites of a state
    """

    kind: Optional[str] = None
    requisites: List[RequisiteNode] = field(default_factory=list)

    def get_symbol(self) -> str:
        return "R"

    def get_id(self) -> Optional[str]:
        return self.kind

    def set_key(self: "RequisitesNode", key: str) -> AstNode:
        """
        Set the kind of the requisite

        :param key: the kind to set
        :return: the node that was updated
        """
        self.kind = key
        return self

    def add(self: "RequisitesNode") -> AstNode:
        """
        Add a requisite entry to the tree, the key and value will come later

        :return: the added node
        """
        self.requisites.append(RequisiteNode(parent=self))
        return self.requisites[-1]

    def get_children(self: "RequisitesNode") -> Sequence[AstNode]:
        """
        Returns all the children nodes
        """
        return self.requisites


@dataclass
class StateCallNode(AstMapNode):
    """
    Node representing the state call part of the state definition.
    For instance it represents the following part:

    .. code-block:: yaml

            file.managed:
              - name: /etc/libvirt/libvirtd.conf
              - source: salt://libvirt/libvirtd.conf

    .. code-block:: yaml

          libvirt_config:
            file.managed:
              - name: /etc/libvirt/libvirtd.conf
              - source: salt://libvirt/libvirtd.conf
    """

    name: Optional[str] = None
    parameters: List[StateParameterNode] = field(default_factory=list)
    requisites: List[RequisitesNode] = field(default_factory=list)

    def get_symbol(self) -> str:
        return "C"

    def get_id(self) -> Optional[str]:
        return self.name

    def add(self: "StateCallNode") -> AstNode:
        """
        Add an entry to the tree, the key and value will come later

        :return: the added node
        """
        self.parameters.append(StateParameterNode(parent=self))
        return self.parameters[-1]

    def set_key(self: "StateCallNode", key: str) -> AstNode:
        """
        Set the name
        """
        self.name = key
        return self

    def convert(self: "StateCallNode", param: StateParameterNode, name: str) -> AstNode:
        """
        Convert a parameter entry to a requisite one
        """
        self.parameters.remove(param)
        self.requisites.append(RequisitesNode(kind=name, parent=self))
        self.requisites[-1].start = param.start
        return self.requisites[-1]

    def get_children(self: "StateCallNode") -> Sequence[AstNode]:
        """
        Returns all the children nodes
        """
        return cast(List[AstNode], self.parameters) + cast(
            List[AstNode], self.requisites
        )


@dataclass
class StateNode(AstMapNode):
    """
    Node representing a state definition like the following.

    .. code-block:: yaml

          libvirt_config:
            file.managed:
              - name: /etc/libvirt/libvirtd.conf
              - source: salt://libvirt/libvirtd.conf
    """

    identifier: Optional[str] = None
    states: List[StateCallNode] = field(default_factory=list)

    def get_symbol(self) -> str:
        return "S"

    def get_id(self) -> Optional[str]:
        return self.identifier

    def add(self: "StateNode") -> AstNode:
        """
        Add a key token to the tree, the value will come later

        :return: the added node
        """
        self.states.append(StateCallNode(parent=self))
        return self.states[-1]

    def set_key(self: "StateNode", key: str) -> AstNode:
        """
        Set the identifier of the node. If the ikey is one of include or
        extend, tell the parent to handle it.

        :return: the node where the key has been set.
        """
        if key in ["include", "extend"] and isinstance(self.parent, Tree):
            return self.parent.convert(self, key)
        self.identifier = key
        return self

    def get_children(self: "StateNode") -> Sequence[AstNode]:
        """
        Returns all the children nodes
        """
        return self.states


@dataclass
class ExtendNode(AstMapNode):
    """
    Node representing an ``extend`` declaration
    """

    states: List[StateNode] = field(default_factory=list)

    def get_symbol(self) -> str:
        return "E"

    def add(self: "ExtendNode") -> AstNode:
        """
        Add a key token to the tree, the value will come later

        :return: the added node
        """
        self.states.append(StateNode(parent=self))
        return self.states[-1]

    def get_children(self: "ExtendNode") -> Sequence[AstNode]:
        """
        Returns all the children nodes
        """
        return self.states


@dataclass
class Tree(AstMapNode):
    """
    Node representing the whole SLS file
    """

    includes: Optional[IncludesNode] = None
    extend: Optional[ExtendNode] = None
    states: List[StateNode] = field(default_factory=list)

    def get_symbol(self) -> str:
        return "T"

    def add(self: "Tree") -> AstNode:
        """
        Add a key token to the tree, the value will come later

        :return: the added node
        """
        self.states.append(StateNode(parent=self))
        return self.states[-1]

    def convert(self: "Tree", state: StateNode, name: str) -> AstNode:
        """
        Convert a child state node into the proper node type depending on the
        name.

        :param state: the state node to change
        :param name: the name of the state node

        :return: the state node if no change was needed or the newly created
            node
        """
        self.states.remove(state)

        if name == "include":
            self.includes = IncludesNode(parent=self)
            self.includes.start = state.start
            return self.includes

        if name == "extend":
            self.extend = ExtendNode(parent=self)
            self.extend.start = state.start
            return self.extend
        return self

    def get_children(self: "Tree") -> Sequence[AstNode]:
        """
        Returns all the children nodes
        """
        includes = [self.includes] if self.includes else []
        extend = [self.extend] if self.extend else []

        return (
            cast(List[AstNode], includes)
            + cast(List[AstNode], extend)
            + cast(List[AstNode], self.states)
        )


@dataclass(init=False, eq=False)
class TokenNode(AstNode):
    """
    Wrapper node for unprocessed yaml tokens
    """

    token: yaml.Token = field(default_factory=lambda: yaml.Token(1, 1))

    def __init__(self: "TokenNode", token: yaml.Token) -> None:
        super().__init__(
            start=Position(line=token.start_mark.line, col=token.start_mark.column),
            end=Position(line=token.end_mark.line, col=token.end_mark.column),
        )
        self.token = token

    def __eq__(self, other):
        if not isinstance(other, TokenNode) or not isinstance(
            self.token, type(other.token)
        ):
            return False

        is_scalar = isinstance(self.token, yaml.ScalarToken)
        scalar_equal = is_scalar and self.token.value == other.token.value
        return super().__eq__(other) and (scalar_equal or not is_scalar)
