import logging
import os

import pytest
import pytest_asyncio
from aiogram import Dispatcher, Bot
from alembic.command import upgrade
from alembic.config import Config as AlembicConfig
from dataclass_factory import Factory
from mockito import mock
from redis.asyncio.client import Redis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, close_all_sessions
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from common.config.models.paths import Paths
from db.config.models.db import RedisConfig
from db.dao.holder import HolderDao
from db.fatory import create_lock_factory
from shvatka.clients.file_storage import FileStorage
from shvatka.scheduler import Scheduler
from shvatka.utils.key_checker_lock import KeyCheckerFactory
from tests.fixtures.conftest import fixtures_resource_path  # noqa: F401
from tests.fixtures.player import harry, hermione, ron, author  # noqa: F401
from tests.fixtures.scn_fixtures import simple_scn  # noqa: F401
from tests.mocks.config import DBConfig
from tgbot.config.models.main import TgBotConfig
from tgbot.main_factory import (
    create_dispatcher, create_scheduler, create_redis,
)
from tgbot.username_resolver.user_getter import UserGetter

logger = logging.getLogger(__name__)


@pytest_asyncio.fixture
async def dao(session: AsyncSession, redis: Redis) -> HolderDao:
    dao_ = HolderDao(session=session, redis=redis)
    await clear_data(dao_)
    return dao_


@pytest_asyncio.fixture
async def check_dao(session: AsyncSession, redis: Redis) -> HolderDao:
    dao_ = HolderDao(session=session, redis=redis)
    return dao_


async def clear_data(dao: HolderDao):
    await dao.poll.delete_all()
    await dao.waiver.delete_all()
    await dao.level.delete_all()
    await dao.level_time.delete_all()
    await dao.key_time.delete_all()
    await dao.game.delete_all()
    await dao.player_in_team.delete_all()
    await dao.team.delete_all()
    await dao.chat.delete_all()
    await dao.player.delete_all()
    await dao.user.delete_all()
    await dao.commit()


@pytest_asyncio.fixture
async def session(pool: sessionmaker) -> AsyncSession:
    async with pool() as session_:
        yield session_


@pytest.fixture(scope="session")
def pool(postgres_url: str) -> sessionmaker:
    engine = create_async_engine(url=postgres_url)
    pool_ = sessionmaker(bind=engine, class_=AsyncSession,
                         expire_on_commit=False, autoflush=False)
    yield pool_
    close_all_sessions()


@pytest.fixture(scope="session")
def postgres_url() -> str:
    postgres = PostgresContainer("postgres:11")
    if os.name == "nt":  # TODO workaround from testcontainers/testcontainers-python#108
        postgres.get_container_host_ip = lambda: 'localhost'
    try:
        postgres.start()
        postgres_url_ = postgres.get_connection_url().replace("psycopg2", "asyncpg")
        logger.info("postgres url %s", postgres_url_)
        yield postgres_url_
    finally:
        postgres.stop()


@pytest.fixture(scope="session")
def redis() -> Redis:
    redis_container = RedisContainer("redis:latest")
    if os.name == "nt":  # TODO workaround from testcontainers/testcontainers-python#108
        redis_container.get_container_host_ip = lambda: 'localhost'
    try:
        redis_container.start()
        url = redis_container.get_container_host_ip()
        port = redis_container.get_exposed_port(redis_container.port_to_expose)
        r = create_redis(RedisConfig(url=url, port=int(port), ))
        yield r
    finally:
        redis_container.stop()


@pytest.fixture(autouse=True)
def patch_api_config(bot_config: TgBotConfig, postgres_url: str, redis: Redis):
    bot_config.db = DBConfig(postgres_url)
    bot_config.redis.url = redis.connection_pool.connection_kwargs["host"]
    bot_config.redis.port = redis.connection_pool.connection_kwargs["port"]
    bot_config.redis.db = redis.connection_pool.connection_kwargs["db"]


@pytest_asyncio.fixture(scope="session")
async def scheduler(pool: sessionmaker, redis: Redis, bot: Bot, bot_config: TgBotConfig):
    async with create_scheduler(
        pool=pool, redis=redis, bot=bot, redis_config=bot_config.redis,
        game_log_chat=bot_config.bot.log_chat,
    ) as sched:
        yield sched


@pytest.fixture(scope="session")
def locker() -> KeyCheckerFactory:
    return create_lock_factory()


@pytest.fixture(scope="session")
def dp(
    pool: sessionmaker, bot_config, user_getter: UserGetter,
    dcf: Factory, redis: Redis, scheduler: Scheduler, locker: KeyCheckerFactory,
) -> Dispatcher:
    return create_dispatcher(
        config=bot_config, user_getter=user_getter, dcf=dcf, pool=pool,
        redis=redis, scheduler=scheduler, locker=locker,
    )


@pytest.fixture(scope="session")
def user_getter() -> UserGetter:
    dummy = mock(UserGetter)
    return dummy


@pytest.fixture(scope="session")
def bot(bot_config) -> Bot:
    dummy = mock(Bot)
    setattr(dummy, "id", int(bot_config.bot.token.split(":")[0]))
    return dummy


@pytest.fixture(scope="session")
def alembic_config(postgres_url: str, paths: Paths) -> AlembicConfig:
    alembic_cfg = AlembicConfig(str(paths.app_dir.parent / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(paths.app_dir.parent / "db" / "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    return alembic_cfg


@pytest.fixture(scope="session", autouse=True)
def upgrade_schema_db(alembic_config: AlembicConfig):
    upgrade(alembic_config, "head")


@pytest.fixture(scope="session")
def file_storage() -> FileStorage:
    return mock(FileStorage)
