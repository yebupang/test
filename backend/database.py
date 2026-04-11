from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from config import get_settings
import logging

logger = logging.getLogger(__name__)
settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False},
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    from models.portfolio import Account, Position, WatchList, PriceHistory, SyncLog  # noqa
    from models.strategy import Strategy, PositionRule, StrategyAlert  # noqa
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _run_migrations()


async def _run_migrations():
    """对已存在的数据库补充新增列（SQLite 不支持 IF NOT EXISTS，用 try/except）"""
    migrations = [
        # 2025-04: 货币基金标记列
        "ALTER TABLE positions ADD COLUMN is_cash_equivalent BOOLEAN DEFAULT 0",
    ]
    async with engine.begin() as conn:
        for sql in migrations:
            try:
                await conn.execute(text(sql))
                logger.info(f"迁移成功: {sql}")
            except Exception:
                # 列已存在时 SQLite 会抛异常，忽略即可
                pass
