"""
Module defining and building an AST from the SLS file.
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional, Tuple, Type, TypeVar, Union, cast

import yaml
from jinja2 import Environment, FileSystemLoader
from yaml.tokens import BlockEndToken, ScalarToken

from salt_lsp.magic_responder import MagicResponder
from salt_lsp.types import (
    AstMapNode,
    AstNode,
    IncludeNode,
    IncludesNode,
    NullUndefined,
    Position,
    RequisiteNode,
    RequisitesNode,
    StateCallNode,
    StateNode,
    StateParameterNode,
    TokenNode,
    Tree,
)
from salt_lsp.utils import FileUri

log = logging.getLogger(__name__)

T = TypeVar("T", bound=AstMapNode)
T2 = TypeVar("T2", bound=AstNode)


class Parser:
    """
    SLS file parser class
    """

    def _is_last_breadcrumb(
        self: Parser, classType: Union[type, Tuple[type, ...]]
    ) -> bool:
        if len(self._breadcrumbs) == 0:
            return False
        return isinstance(self._breadcrumbs[-1], classType)

    def __init__(self: Parser, rootUri: FileUri, document: str) -> None:
        """
        Create a parser object for an SLS file.

        :param document: the content of the SLS file to parse
        """
        self.document = document
        self.rootUri = rootUri
        self._tree = Tree()
        self._breadcrumbs: List[AstNode] = [self._tree]
        self._block_starts: List[
            Tuple[
                Union[
                    yaml.BlockMappingStartToken,
                    yaml.BlockSequenceStartToken,
                    yaml.FlowSequenceStartToken,
                    yaml.FlowMappingStartToken,
                    yaml.Token,
                ],
                AstNode,
            ],
        ] = []
        self._next_scalar_as_key = False
        #: flag for _process_token that the preceding token was a ValueToken
        #: => if applicable, the next token will be a value, unless a block is
        #:    started
        self._next_token_is_value = False
        self._unprocessed_tokens: Optional[List[TokenNode]] = None
        self._last_start: Optional[Position] = None
        # Sometime we need to adjust the column index to deal with not really valid yaml
        # but accepted by Salt
        self._col_adjustment = 0

    def _process_token_star_start(self: Parser, token: yaml.Token) -> None:
        # Store which block start corresponds to what breadcrumb to help
        # handling end block tokens
        if len(self._breadcrumbs) > 0 and (
            (
                len(self._block_starts) > 0
                and self._block_starts[-1][1] != self._breadcrumbs[-1]
            )
            or len(self._block_starts) == 0
        ):
            log.debug(f"Adding {(token, self._breadcrumbs[-1])} to _block_starts")
            self._block_starts.append((token, self._breadcrumbs[-1]))
        # a block is starting, so the next token cannot be a value, it will
        # be a complex type instead
        self._next_token_is_value = False

    def _process_unprocessed_tokens(self: Parser, token: yaml.Token) -> None:
        assert self._unprocessed_tokens is not None
        if not self._is_last_breadcrumb(StateParameterNode) or not isinstance(
            token, yaml.BlockEndToken
        ):
            self._unprocessed_tokens.append(TokenNode(token=token))
        if isinstance(
            token,
            (
                yaml.BlockMappingStartToken,
                yaml.BlockSequenceStartToken,
                yaml.FlowSequenceStartToken,
                yaml.FlowMappingStartToken,
            ),
        ):
            self._breadcrumbs.append(self._unprocessed_tokens[-1])
            self._block_starts.append((token, self._breadcrumbs[-1]))
            # a block is starting, so the next token cannot be a value, it
            # will be a complex type instead
            self._next_token_is_value = False

    def _process_star_end(self: Parser, token: yaml.Token, token_end: Position) -> None:
        if len(self._block_starts) == 0 or len(self._breadcrumbs) == 0:
            log.error(
                "Reached a %s but either no block starts "
                "(len(self._block_starts) = %d) or no breadcrumbs "
                "(len(self._breadcrumbs) = %d) are present",
                type(token).__name__,
                len(self._block_starts),
                len(self._breadcrumbs),
            )
            return
        last_start = self._block_starts.pop()
        last = self._breadcrumbs.pop()
        # pop breadcrumbs until we match the block starts
        closed = last
        while len(self._breadcrumbs) > 0 and closed != last_start[1]:
            log.debug(
                f"last_start = {last_start}\nclosed = {closed}\n"
                f"len(self._breadcrumbs) = {len(self._breadcrumbs)}"
            )
            closed.end = token_end
            closed = self._breadcrumbs.pop()
            # if self._col_adjustment > 0 and type(closed) == StateCallNode
            log.debug(f"now closed = {closed}")
            last = closed

        if not isinstance(last, TokenNode):
            last.end = token_end

        if isinstance(last, StateCallNode):
            # log.debug(self._breadcrumbs)
            # log.debug(self._block_starts)
            if self._col_adjustment > 0:
                log.debug(f"Reseting current adjustment { self._col_adjustment } to 0")
                self._col_adjustment = 0
            pass
        if (
            isinstance(last, StateParameterNode)
            and self._unprocessed_tokens is not None
        ):
            if len(self._unprocessed_tokens) == 1 and isinstance(
                self._unprocessed_tokens[0].token, yaml.ScalarToken
            ):
                last.value = self._unprocessed_tokens[0].token.value
            else:
                for unprocessed in self._unprocessed_tokens:
                    unprocessed.parent = last
                last.value = self._unprocessed_tokens
            self._unprocessed_tokens = None

    def _process_token_blockEntry(
        self: Parser, token: yaml.Token, token_start: Position
    ) -> None:
        # Create the state parameter, include and requisite before the dict
        # since those are dicts in lists
        same_level = (
            len(self._breadcrumbs) > 0
            and self._breadcrumbs[-1].start
            and self._breadcrumbs[-1].start.col
            == (token.start_mark.column + self._col_adjustment)
        )
        if same_level:
            if (
                type(token) == yaml.BlockEntryToken
                and type(self._breadcrumbs[-1]) == StateCallNode
            ):
                assert self._breadcrumbs[-1].start is not None
                self._col_adjustment = self._breadcrumbs[-1].start.col
                log.warning(
                    "Seems that you have misformated yaml, Salt seems to be able to"
                    " deal with that so let's do that too"
                )
                if len(self._breadcrumbs) > 0:
                    start_mark = token.start_mark
                    end_mark = token.end_mark
                    fakeToken = yaml.BlockMappingStartToken(start_mark, end_mark)
                    # Because of mis-alignement we didn't get a
                    # BlockSequenceStartToken nor
                    # a BlockMappingStartToken added to _block_starts

                    log.debug(
                        f"Adding {(fakeToken, self._breadcrumbs[-1])} to _block_starts"
                    )
                    self._block_starts.append((fakeToken, self._breadcrumbs[-1]))
            else:
                log.warning(
                    "Same level with token %s , token_start = %s"
                    "(len(self._block_starts) = %d) "
                    "(len(self._breadcrumbs) = %d) poping the last breadcrumb: %s.",
                    type(token).__name__,
                    token_start,
                    len(self._block_starts),
                    len(self._breadcrumbs),
                    self._breadcrumbs[-1],
                )
                self._breadcrumbs.pop().end = token_start
                log.warning(
                    "Now "
                    "(len(self._block_starts) = %d) "
                    "(len(self._breadcrumbs) = %d).",
                    len(self._block_starts),
                    len(self._breadcrumbs),
                )
        if len(self._breadcrumbs) > 0:
            if self._is_last_breadcrumb((StateCallNode, IncludesNode, RequisitesNode)):
                # This is only to please mypy we are sure because of the call above that
                # the last breadcrumb is of one the three class above.
                # We shouldn't expect that current is of type RequisitesNode
                current = cast(
                    RequisitesNode,
                    self._breadcrumbs[-1],
                )
                self._breadcrumbs.append(current.add())
                self._breadcrumbs[-1].start = token_start
        else:
            log.warning(
                "Don't quite know what to do with token %s "
                "(len(self._block_starts) = %d) or no breadcrumbs "
                "(len(self._breadcrumbs) = %d) are present",
                type(token).__name__,
                len(self._block_starts),
                len(self._breadcrumbs),
            )

    def _process_token_scalar(
        self: Parser,
        token: yaml.ScalarToken,
        token_start: Position,
        token_end: Position,
    ) -> None:
        if self._next_scalar_as_key and getattr(self._breadcrumbs[-1], "set_key"):
            changed = getattr(self._breadcrumbs[-1], "set_key")(token.value)
            # If the changed node isn't the same than the one we called the
            # function on, that means that the node had to be converted and
            # we need to update the breadcrumbs too.
            if changed != self._breadcrumbs[-1]:
                old = self._breadcrumbs.pop()
                self._breadcrumbs.append(changed)
                self._block_starts = [
                    (block[0], changed) if block[1] == old else block
                    for block in self._block_starts
                ]

            self._next_scalar_as_key = False
        else:
            if self._is_last_breadcrumb(IncludeNode):
                current = cast(IncludeNode, self._breadcrumbs[-1])
                current.value = token.value
                self._breadcrumbs[-1].end = token_end
                self._breadcrumbs.pop()
            if self._is_last_breadcrumb(RequisiteNode):
                current2 = cast(RequisiteNode, self._breadcrumbs[-1])
                current2.reference = token.value
            # If the user hasn't typed the ':' yet, then the state
            # parameter will come as a scalar
            current3 = cast(StateParameterNode, self._breadcrumbs[-1])
            if self._is_last_breadcrumb(StateParameterNode) and current3.name is None:
                current3.name = token.value
            if self._is_last_breadcrumb((StateNode, Tree)):
                current4 = cast(StateNode, self._breadcrumbs[-1])
                new_node = current4.add()
                new_node.start = token_start
                new_node.end = token_end
                if getattr(new_node, "set_key"):
                    getattr(new_node, "set_key")(token.value)

                # this scalar token is actually the plain value of the
                # previous key and "a new thing" starts with the next token
                # => pop the current breadcrumb as it is now processed
                if self._next_token_is_value:
                    last = self._breadcrumbs.pop()
                    if last.end is None:
                        last.end = token_end

        self._next_token_is_value = False

    def _process_token(self: Parser, token: yaml.Token) -> None:
        """
        Process one token
        """
        token_start = Position(line=token.start_mark.line, col=token.start_mark.column)
        token_end = Position(line=token.end_mark.line, col=token.end_mark.column)
        if isinstance(token, yaml.StreamStartToken):
            self._tree.start = token_start
        if isinstance(token, yaml.StreamEndToken):
            self._tree.end = token_end

        log.debug(
            f"Current token is {token} "
            f"start ({token.start_mark.line + 1}, {token.start_mark.column + 1})"
        )

        if isinstance(
            token,
            (
                yaml.BlockMappingStartToken,
                yaml.BlockSequenceStartToken,
                yaml.FlowSequenceStartToken,
                yaml.FlowMappingStartToken,
            ),
        ):
            self._process_token_star_start(token)

        if isinstance(token, yaml.ValueToken):
            self._next_token_is_value = True
            if (
                self._is_last_breadcrumb(StateParameterNode)
                and not self._unprocessed_tokens
            ):
                self._unprocessed_tokens = []
                # We don't need to do anything else with this token,
                # just flag the next tokens to be simply collected
                return

        if self._unprocessed_tokens is not None:
            self._process_unprocessed_tokens(token)

        if isinstance(
            token,
            (
                yaml.BlockEndToken,
                yaml.FlowSequenceEndToken,
                yaml.FlowMappingEndToken,
            ),
        ):
            self._process_star_end(token, token_end)

        if self._unprocessed_tokens is not None:
            # If self._unprocessed_tokens is set then we don't have
            # Salt-specific data token to process
            # reset the flag that the next token is a value, as the current
            # token has now been put into self._unprocessed_tokens and will be
            # taken care of in the next sweep
            self._next_token_is_value = False
            return

        if isinstance(token, yaml.KeyToken):
            self._next_scalar_as_key = True
            if self._is_last_breadcrumb(AstMapNode) and not self._is_last_breadcrumb(
                (RequisiteNode, StateParameterNode)
            ):
                current = cast(
                    StateCallNode,
                    self._breadcrumbs[-1],
                )
                self._breadcrumbs.append(current.add())
                if self._last_start:
                    self._breadcrumbs[-1].start = self._last_start
                    self._last_start = None
                else:
                    self._breadcrumbs[-1].start = token_start

        if isinstance(token, yaml.BlockEntryToken):
            self._process_token_blockEntry(token, token_start)

        if isinstance(token, yaml.ScalarToken):
            token = cast(yaml.ScalarToken, token)
            self._process_token_scalar(token, token_start, token_end)

    def parse(self) -> Tree:
        """
        Generate the Abstract Syntax Tree for a ``jinja|yaml`` rendered SLS
        file.

        :return: the generated AST
        :raises ValueException: for any other renderer but ``jinja|yaml``
        """
        saved_level = log.getEffectiveLevel()
        # Bump above DEBUG to avoid too much debug when not debugging the parser
        if saved_level == logging.DEBUG:
            log.setLevel(logging.INFO)
        grains = MagicResponder("grains")
        pillar = MagicResponder("pillar")
        salt = MagicResponder("salt")
        filtered = []
        for line in self.document.split("\n"):
            if not re.search(r"{% from", line):
                filtered.append(line)

            else:
                filtered.append("# skipped line")

        # Render the file through Jinja to avoid parsing error
        t = Environment(
            loader=FileSystemLoader([self.rootUri.path]),
            undefined=NullUndefined,
        ).from_string("\n".join(filtered))

        # We usually have pillar, grains and salt variables that Jinja can't resolve on
        # it's own
        params = {
            "grains": grains,
            "pillar": pillar,
            "salt": salt,
        }
        doc = t.render(params)
        tokens = yaml.scan(doc)

        token = None
        try:
            for token in tokens:
                self._process_token(token)
        except yaml.scanner.ScannerError as err:
            log.warning(err)
            if token:
                log.debug(token)
                # Properly close the opened blocks
                for node in reversed(self._breadcrumbs):
                    log.debug(node)
                    if (
                        node.start is not None
                        and err.context_mark is not None
                        and err.context_mark.column < node.start.col
                    ):
                        self._process_token(
                            BlockEndToken(
                                start_mark=err.context_mark,
                                end_mark=err.context_mark,
                            )
                        )
                    elif (
                        node.start is not None
                        and err.context_mark is not None
                        and err.context_mark.column == node.start.col
                    ):
                        self._process_token(
                            BlockEndToken(
                                start_mark=err.context_mark,
                                end_mark=err.context_mark,
                            )
                        )
                        if err.problem_mark is not None:
                            value = self.document[
                                err.context_mark.index : err.problem_mark.index
                            ].strip("\r\n")
                            error_token = ScalarToken(
                                value=value,
                                start_mark=err.context_mark,
                                end_mark=err.problem_mark,
                                plain=True,
                                style=None,
                            )
                            log.debug(error_token)
                            self._process_token(error_token)
                    elif err.problem_mark is not None:
                        node.end = Position(
                            line=err.problem_mark.line,
                            col=err.problem_mark.column,
                        )
            log.setLevel(saved_level)
            return self._tree
        log.setLevel(saved_level)
        return self._tree


def parse(uri: FileUri, document: str) -> Tree:
    """
    Generate the Abstract Syntax Tree for a ``jinja|yaml`` rendered SLS file.

    :param uri: the root uri of workspace where the file parsed is located
    :param source: the source of the SLS file to parse
    :return: the generated AST
    :raises ValueException: for any other renderer but ``jinja|yaml``
    """
    return Parser(uri, document).parse()
