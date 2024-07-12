import dataclasses
import logging
import pygments
import pygments.formatters
import pygments.lexers
import sqlalchemy.ext.asyncio
import sqlparse  # type: ignore[import-untyped]
import sys
import textwrap
from dataclasses import dataclass
from types import TracebackType
from typing import Any
from typing import Self

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@dataclass
class CapSQL:
    """A context manager that captures queries executed by a SQLAlchemy engine.

    This is inspired by pytest's standard ``caplog`` and ``capsys`` fixtures, which
    capture logging, stdout, and stderr output; but in this case, :class:`CapSQL`
    captures SQL emitted by a SQLAlchemy engine.

    Although SQLAlchemy has some capability out of the box for showing generated SQL
    queries (using "echo" mode, ``print(statement.compile())``, etc.), it has several
    issues/limitations:

    1.  Echo mode emits output continuously, and when your tests often have a lot of
        initial setup, most of the output ends up being noise compared to the part you
        really want to see.
    2.  Echo mode emits output to a logger, and programmatically accessing the logs
        basically requires painstakingly careful extraction/filtering/parsing/siphoning
        of the relevant logs from the sea of noise.
    3.  Query stringification is not pretty-printed, so the dumped query text is an
        illegibly jumbled mess.
    4.  Using ``statement.compile()`` / ``str(statement)`` often neglects the subsequent
        followup queries that are executed automatically by SQLAlchemy, such as when
        using the ubiquitous :meth:`sqlalchemy.orm.selectinload`, leading to blindspots
        about what's really going on when you perform a query.  "Why is this query slow?
        It's only querying X, according to ``print(str(statement))``..." In actuality,
        there may be an entire cascade of followup queries happening, and you wouldn't
        know unless you look really closely at the noisy echo-mode output mess and
        realize where the additional queries are originating from.

    :class:`CapSQL` solves these issues as follows:

    1.  Capture only what you want, when you want it, thanks to :class:`CapSQL` being
        usable as a context manager (``with capsql: ...``).
    2.  Collect emitted SQL element objects and raw statements into
        :attr:`CapSQL.elements` and :attr:`CapSQL.statements` (respectively) for
        programmatic inspection.
    3.  Pretty-print queries using :mod:`sqlformat`; and also optionally echo to the
        terminal with color, acting as an improved version of SQLAlchemy's built in
        echo mode.
    4.  Capture followup queries that are executed automatically by SQLAlchemy, e.g.
        when using :meth:`sqlalchemy.orm.selectinload`, eliminating blindspots.
    """

    engine: sqlalchemy.ext.asyncio.AsyncEngine

    _: dataclasses.KW_ONLY

    # Settings:

    color: bool = True  # TODO: autodetect based on term caps
    """If set, colorize terminal output using Pygments.

    Todo: auto-detect setting based on terminal capabilities.
    """

    echo: bool = False
    """If set, print/echo statements to stderr."""

    log: bool = False
    """Similar to :attr:`echo` except that it uses :mod:`logging` instead of
    :meth:`print`.
    """

    show_params: bool = False

    logger: logging.Logger = logger

    pretty: bool = True
    """If set, pretty-print/format SQL statements using :mod:`sqlparse`."""

    # Captured SQL:
    elements: list[sqlalchemy.sql.Executable] = dataclasses.field(default_factory=list)
    statements: list[str] = dataclasses.field(default_factory=list)

    @property
    def text(self) -> str:
        return '\n\n'.join(self.statements)

    def clear(self) -> None:
        self.elements = []
        self.statements = []

    def _handle_before_execute(
        self,
        conn: sqlalchemy.engine.Connection,  # pylint: disable=unused-argument
        clauseelement: sqlalchemy.sql.Executable,
        multiparams: Any,  # pylint: disable=unused-argument
        params: Any,  # pylint: disable=unused-argument
        execution_options: dict[str, Any],  # pylint: disable=unused-argument
    ) -> None:
        self.elements.append(clauseelement)

    def _colorize(
        self,
        statement: str,
    ) -> str:
        return pygments.highlight(
            statement,
            pygments.lexers.SqlLexer(),  # pylint: disable=no-member
            pygments.formatters.TerminalFormatter(),  # pylint: disable=no-member
        )

    def _output(
        self,
        message: str,
    ) -> None:
        if self.echo:
            print(message, file=sys.stderr)

        if self.log:
            if self.pretty:
                # TBD: when the SQL query/statement is formatted across multiple lines,
                # indenting the log message tends to produce cleaner output - at least
                # when using the standard pytest logging config, which prefixes the
                # first line of log messages with `INFO ...`, which causes misalignment
                # if we're not careful.
                log_message = '\n' + textwrap.indent(message, '    ')
            else:
                log_message = message
            self.logger.info(log_message)

    def _handle_before_cursor_execute(
        self,
        conn: sqlalchemy.engine.Connection,  # pylint: disable=unused-argument
        cursor: sqlalchemy.engine.interfaces.DBAPICursor,  # pylint: disable=unused-argument
        statement: str,
        parameters: Any,
        context: sqlalchemy.engine.ExecutionContext,  # pylint: disable=unused-argument
        executemany: bool,  # pylint: disable=unused-argument
    ) -> None:
        if self.pretty:
            statement = sqlparse.format(
                statement,
                reindent=True,
                reindent_aligned=False,  # noop?
            )
        if self.show_params:
            statement += f'\n-- params: {parameters!r}'
        self.statements.append(statement)
        # TODO: capture params too?

        if self.echo or self.log:
            self._output(self._colorize(statement) if self.color else statement)

    def __enter__(self) -> Self:
        # TODO: gracefully deal with reentrancy
        sqlalchemy.event.listen(
            self.engine.sync_engine,
            'before_execute',
            self._handle_before_execute,
        )
        sqlalchemy.event.listen(
            self.engine.sync_engine,
            'before_cursor_execute',
            self._handle_before_cursor_execute,
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        sqlalchemy.event.remove(
            self.engine.sync_engine,
            'before_execute',
            self._handle_before_execute,
        )
        sqlalchemy.event.remove(
            self.engine.sync_engine,
            'before_cursor_execute',
            self._handle_before_cursor_execute,
        )


__all__ = [
    'CapSQL',
    'logger',
]
