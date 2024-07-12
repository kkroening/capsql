import capsql as _capsql
import pytest
import sqlalchemy
import sqlalchemy.ext.asyncio
import sqlalchemy.ext.declarative
from textwrap import dedent

_Base = sqlalchemy.orm.declarative_base()


class User(_Base):
    __tablename__ = 'users'
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    name = sqlalchemy.Column(sqlalchemy.String(50))
    email = sqlalchemy.Column(sqlalchemy.String(50))


@pytest.fixture()
async def engine() -> sqlalchemy.ext.asyncio.AsyncEngine:
    engine = sqlalchemy.ext.asyncio.create_async_engine(
        'sqlite+aiosqlite:///:memory:', echo=False
    )
    try:
        async with engine.begin() as conn:
            await conn.run_sync(_Base.metadata.create_all)
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def session(engine):
    async with sqlalchemy.ext.asyncio.AsyncSession(
        engine, expire_on_commit=False
    ) as session:
        yield session


async def test__init(engine):
    capsql = _capsql.CapSQL(engine)
    assert capsql.engine is engine
    assert capsql.color is True
    assert capsql.echo is False
    assert capsql.log is False
    assert capsql.show_params is False
    assert capsql.pretty is True
    assert isinstance(capsql.elements, list)
    assert isinstance(capsql.statements, list)


class Test__capture:
    async def test__basic(self, session, faker):
        capsql = _capsql.CapSQL(engine=session.bind)

        with capsql:
            async with session.begin():
                session.add(User(name=faker.name(), email=faker.email()))

        expected_statements = [
            dedent(
                '''
                INSERT INTO users (name, email)
                VALUES (?, ?)
                '''
            ).strip(),
        ]
        assert capsql.statements == expected_statements

        (await session.scalars(sqlalchemy.select(User))).all()
        assert capsql.statements == expected_statements

        with capsql:
            expr = sqlalchemy.select(User).filter_by(name=faker.name())
            (await session.scalars(expr)).all()
        expected_statements.append(
            dedent(
                '''
                SELECT users.id,
                       users.name,
                       users.email
                FROM users
                WHERE users.name = ?
                '''
            ).strip()
        )
        assert capsql.statements == expected_statements
        expected_text = '\n\n'.join(expected_statements)
        assert capsql.text == expected_text

    async def test__show_params(self, session, faker):
        capsql = _capsql.CapSQL(engine=session.bind, show_params=True)

        user = User(name=faker.name(), email=faker.email())
        with capsql:
            async with session.begin():
                session.add(user)

        expected_statements = [
            dedent(
                f'''
                INSERT INTO users (name, email)
                VALUES (?, ?)
                -- params: {user.name, user.email}
                '''
            ).strip(),
        ]
        assert capsql.statements == expected_statements
        expected_text = '\n\n'.join(expected_statements)
        assert capsql.text == expected_text
