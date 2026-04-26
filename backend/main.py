import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from routers import accounts, portfolio, sync, watchlist, strategy
from config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("初始化数据库...")
    await init_db()

    # 如果配置了自动同步，启动定时任务
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from database import AsyncSessionLocal
    from services.sync_service import SyncService
    from services.snapshot_service import SnapshotService

    scheduler = AsyncIOScheduler()

    if settings.sync_interval > 0:
        async def auto_refresh():
            async with AsyncSessionLocal() as db:
                svc = SyncService(db)
                count = await svc.refresh_quotes()
                logger.info(f"自动刷新行情: {count} 条")

        scheduler.add_job(auto_refresh, "interval", seconds=settings.sync_interval)
        logger.info(f"自动行情刷新已启动，间隔 {settings.sync_interval}s")

    # 每日 23:00 UTC 写入资产快照（北京时间次日 7:00，开盘前）
    async def daily_snapshot():
        async with AsyncSessionLocal() as db:
            svc = SnapshotService(db)
            count = await svc.take_daily_snapshot()
            logger.info(f"每日资产快照完成: {count} 行")

    scheduler.add_job(daily_snapshot, "cron", hour=23, minute=0)
    scheduler.start()
    logger.info("每日资产快照已注册（UTC 23:00）")

    logger.info("投资助手后端启动完成 ✓")
    yield
    logger.info("投资助手后端关闭")


app = FastAPI(
    title="投资助手 API",
    description="个人投资决策支持系统 — Phase 2: 交易策略引擎",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(accounts.router)
app.include_router(portfolio.router)
app.include_router(sync.router)
app.include_router(watchlist.router)
app.include_router(strategy.router)


@app.get("/")
async def root():
    return {
        "name": "投资助手 API",
        "version": "0.1.0",
        "docs": "/docs",
        "status": "running",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
