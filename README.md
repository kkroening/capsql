# CapSQL: SQL Query Capturing for SQLAlchemy

## Introduction

`CapSQL` is a context manager that captures and logs queries executed by a SQLAlchemy engine.

Inspired by pytest's standard ``caplog`` and ``capsys`` fixtures (which capture logging, stdout, and stderr output), `CapSQL` captures SQL emitted by a SQLAlchemy engine while addressing limitations of SQLAlchemy's built-in logging/echo capability.

This is primarily aimed at unit testing to get significantly better debug logging, and to make assertions against expected query generation.

## Quickstart

#### Basic usage:

```python
from capsql import CapSQL
...
engine: sqlalchemy.ext.asyncio.AsyncEngine
session: sqlalchemy.ext.asyncio.AsyncSession

expr = session.scalars(select(User).filter_by(name='Bob'))
with CapSQL(engine) as capsql:
    users = (await session.scalars(expr)).all()

print(capsql.statements[0])
```

Output:

```sql
SELECT users.id,
       users.name,
       users.email
FROM users
WHERE users.name = ?
```

#### Echo mode:

```python
with CapSQL(engine, echo=True) as capsql:
    ...
```

(Same output as before but without having to `print`)

## Features

`CapSQL` improves upon SQLAlchemy's native query logging and output mechanisms by offering:

1. **Selective Query Capturing**: Capture only the SQL queries of interest, eliminating noise from setup or unrelated operations.
2. **Enhanced Query Inspection**: Queries are collected for programmatic inspection, allowing for detailed analysis and assertions in tests.
3. **Pretty-Printed SQL**: Queries are formatted for readability, making it easier to understand complex SQL statements, with optional terminal color.
4. **Database-specific Query Analysis**: Connection-level SQL is captured for the exact target database, rather than the SQLAlchemy's higher-level, database-neutral representation which differs from the actual queries SQLAlchemy emits at the connection level.
5. **Automatic Follow-Up Query Capturing**: Automatically captures follow-up queries triggered by SQLAlchemy, such as those from `selectinload`, removing blindspots in understanding query performance and behavior.
6. **Integration with Logging**: Log captured SQL statements if desired, integrating with Python's standard logging system.

> **Note**: Only `sqlalchemy.ext.asyncio.AsyncEngine` is currently supported.  Non-async support would be easy to add.. but if you're not using async, shame on you!

## Configuration

`CapSQL` can be configured with several options to tailor its behavior to your needs:

- `echo`: If `True`, print captured SQL statements to stderr (default is `False`).
- `log`: Similar to `echo`, but uses logging to output SQL statements (default is `False`).
- `show_params`: Set to `True` to include query parameters in the output (default is `False`).
- `pretty`: Enable or disable pretty-printing of SQL statements (default is `True`).
- `color`: Set to `True` to enable colorized terminal output (default is `True`).

Example with options:

```python
capsql = CapSQL(engine=engine, echo=True, pretty=True, show_params=True)
with capsql:
    ...
```

### Entering/exiting the context

You can enter/exit the `with capsql` context manager as much as you like, and it'll only capture while inside the context.

This can particularly useful in tests with nontrivial amounts of setup - e.g. creating sample data, where capturing the SQL emitted from the test setup would just be noise, as in the following example.

## Pytest fixture

```python
@pytest.fixture()
def capsql(engine):
    return CapSQL(engine)


async def test_something(capsql, session):
    expected = await UserFactory.create_batch(3)  # intentionally not captured

    with capsql:
        actual = (await session.scalars(sqlalchemy.select(User))).all()

    assert capsql.statements == [
        dedent(
            '''
            SELECT users.id,
                   users.name,
                   users.email
            FROM users
            WHERE users.name = ?
            '''
        ).strip()
    ]
```

The fixture above initializes the `CapSQL` instance but does not immediately enter it.

Alternatively, the `CapSQL` instance can be entered directly within the fixture:

```python
@pytest.fixture()
def capsql(engine):
    with CapSQL(engine) as capsql:
        yield capsql
```

However, this is often ill-advised because then any tests that use the fixture will capture *all* SQL emitted by the test rather than specific block(s) of code surrounded by `with CapSQL():`.

It can also be useful to define other fixture variants, such as a `logsql` fixture that's conveniently pre-configured with custom logging settings:

```python
@pytest.fixture()
def logsql(capsql):
    return CapSQL(engine, log=True)


async def test_something(logsql, session):
    with logsql:  # e.g. to debug a problem in UserFactory
        expected = await UserFactory.create_batch(3)
    ...
```
