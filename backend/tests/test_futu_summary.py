"""
单元测试：富途港股账户总资产约83万人民币

测试场景：
  富途港股账户持有腾讯(00700)、港交所(00388)、汇丰(00005)三只股票，
  加上基金余额（货币基金）和现金账户。
  以固定汇率 HKD/CNY=0.93 计算：
    股票市值：(440,000 + 56,000 + 180,000) HKD × 0.93 = 628,680 CNY
    基金余额：              100,000          HKD × 0.93 =  93,000 CNY  ← 计入现金侧
    现金账户：              120,000          HKD × 0.93 = 111,600 CNY
    ─────────────────────────────────────────────────────────────────
    总资产：                896,000          HKD × 0.93 = 833,280 CNY ≈ 83万
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from unittest.mock import patch, AsyncMock

# ── 测试数据库（每个函数级别独立的内存 SQLite）────────────────────────────
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
_engine = create_async_engine(TEST_DB_URL, echo=False)
_SessionLocal = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

# ── 固定汇率（避免网络请求影响测试稳定性）────────────────────────────────
FIXED_FX = {"USD": 7.24, "HKD": 0.93, "CNY": 1.0}

# ── 富途账户测试数据 ──────────────────────────────────────────────────────
CASH_HKD = 120_000.0          # 账户现金

EQUITY_POSITIONS = [
    dict(
        symbol="00700", name="腾讯控股", market="HK", currency="HKD",
        quantity=1000, cost_price=380.0, current_price=440.0,
        market_value=440_000.0, unrealized_pnl=60_000.0, unrealized_pnl_pct=15.79,
        is_active=True, is_cash_equivalent=False,
    ),
    dict(
        symbol="00388", name="香港交易所", market="HK", currency="HKD",
        quantity=200, cost_price=250.0, current_price=280.0,
        market_value=56_000.0, unrealized_pnl=6_000.0, unrealized_pnl_pct=12.0,
        is_active=True, is_cash_equivalent=False,
    ),
    dict(
        symbol="00005", name="汇丰控股", market="HK", currency="HKD",
        quantity=3000, cost_price=55.0, current_price=60.0,
        market_value=180_000.0, unrealized_pnl=15_000.0, unrealized_pnl_pct=9.09,
        is_active=True, is_cash_equivalent=False,
    ),
]

FUND_POSITION = dict(
    symbol="_FUND", name="基金余额", market="HK", currency="HKD",
    quantity=1, cost_price=100_000.0, current_price=100_000.0,
    market_value=100_000.0, unrealized_pnl=0.0, unrealized_pnl_pct=0.0,
    is_active=True, is_cash_equivalent=True,
)

# ── 预期计算值 ─────────────────────────────────────────────────────────────
_HKD = FIXED_FX["HKD"]
EXPECTED_EQUITY_MV_CNY   = (440_000 + 56_000 + 180_000) * _HKD   # 628,680
EXPECTED_FUND_CNY        = 100_000 * _HKD                          #  93,000
EXPECTED_CASH_CNY        = CASH_HKD * _HKD + EXPECTED_FUND_CNY    # 204,600
EXPECTED_TOTAL_ASSETS_CNY = EXPECTED_EQUITY_MV_CNY + EXPECTED_CASH_CNY  # 833,280
EXPECTED_EQUITY_RATIO    = round(EXPECTED_EQUITY_MV_CNY / EXPECTED_TOTAL_ASSETS_CNY * 100, 1)


# ════════════════════════════════════════════════════════════════════════════
#  Fixtures
# ════════════════════════════════════════════════════════════════════════════

@pytest_asyncio.fixture(autouse=True)
async def db_tables():
    """每个测试前建表，测试后销毁（保证隔离）。"""
    from database import Base
    from models.portfolio import Account, Position, WatchList, SyncLog  # noqa: F401
    from models.strategy import Strategy, PositionRule, StrategyAlert   # noqa: F401
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db():
    async with _SessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def futu_account(db):
    """插入富途账户 + 三只股票 + 货币基金，并设置现金余额。"""
    from models.portfolio import Account, Position
    acct = Account(
        name="富途港股账户", broker="futu", market="HK",
        currency="HKD", cash_balance=CASH_HKD, cash_currency="HKD",
        is_active=True,
    )
    db.add(acct)
    await db.flush()
    for pos_data in [*EQUITY_POSITIONS, FUND_POSITION]:
        db.add(Position(account_id=acct.id, **pos_data))
    await db.commit()
    return acct


@pytest_asyncio.fixture
async def api_client(db, futu_account):
    """FastAPI 测试客户端：覆盖 DB 依赖，跳过 lifespan 的 init_db 和定时器。"""
    from database import get_db
    from main import app

    async def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db

    with patch("main.init_db", new_callable=AsyncMock), \
         patch("main.settings") as mock_settings:
        mock_settings.sync_interval = 0   # 不启动 APScheduler
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client

    app.dependency_overrides.clear()


# ── 辅助：带固定汇率调用 summary 端点 ────────────────────────────────────
async def _summary(api_client) -> dict:
    with patch(
        "services.market_data.MarketDataService.get_exchange_rates",
        new_callable=AsyncMock, return_value=FIXED_FX,
    ):
        resp = await api_client.get("/portfolio/summary")
    assert resp.status_code == 200, f"接口返回非200: {resp.text}"
    return resp.json()


# ════════════════════════════════════════════════════════════════════════════
#  Test 1 – 总资产约 83 万
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_total_assets_approx_83wan(api_client):
    """总资产折算人民币应约为 833,280（允许 ±1%）。"""
    data = await _summary(api_client)
    actual = data["total_assets_cny"]
    assert abs(actual - EXPECTED_TOTAL_ASSETS_CNY) / EXPECTED_TOTAL_ASSETS_CNY < 0.01, (
        f"总资产偏差超过1%%：期望 {EXPECTED_TOTAL_ASSETS_CNY:.0f} 元，实际 {actual:.0f} 元"
    )


# ════════════════════════════════════════════════════════════════════════════
#  Test 2 – 股票市值折算正确
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_equity_market_value_cny(api_client):
    """股票持仓市值（不含货基）折算人民币：676,000 × 0.93 = 628,680。"""
    data = await _summary(api_client)
    actual = data["total_market_value_cny"]
    assert abs(actual - EXPECTED_EQUITY_MV_CNY) < 1, (
        f"股票市值偏差：期望 {EXPECTED_EQUITY_MV_CNY:.2f}，实际 {actual:.2f}"
    )


# ════════════════════════════════════════════════════════════════════════════
#  Test 3 – 现金侧含货币基金
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cash_cny_includes_fund(api_client):
    """现金侧 = 账户现金 + 货币基金，折算人民币：(120,000 + 100,000) × 0.93 = 204,600。"""
    data = await _summary(api_client)
    actual = data["total_cash_cny"]
    assert abs(actual - EXPECTED_CASH_CNY) < 1, (
        f"现金折算偏差：期望 {EXPECTED_CASH_CNY:.2f}，实际 {actual:.2f}"
    )


# ════════════════════════════════════════════════════════════════════════════
#  Test 4 – 仓位率
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_equity_ratio(api_client):
    """仓位率 = 股票市值 / 总资产 ≈ 75.5%（±0.2%）。"""
    data = await _summary(api_client)
    actual = data["equity_ratio"]
    assert abs(actual - EXPECTED_EQUITY_RATIO) < 0.2, (
        f"仓位率偏差：期望 {EXPECTED_EQUITY_RATIO}%%，实际 {actual}%%"
    )


# ════════════════════════════════════════════════════════════════════════════
#  Test 5 – positions 列表不含货币基金
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_position_count_excludes_fund(api_client):
    """positions 列表应有 3 条（货币基金不暴露给前端）。"""
    data = await _summary(api_client)
    accounts = data["accounts"]
    assert len(accounts) == 1
    positions = accounts[0]["positions"]
    assert len(positions) == 3, (
        f"持仓数量错误：期望3（不含货币基金），实际 {len(positions)}"
    )


# ════════════════════════════════════════════════════════════════════════════
#  Test 6 – 全部持仓在港股市场
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_all_positions_hk_market(api_client):
    """所有股票持仓均属港股（HK），市场占比 100%。"""
    data = await _summary(api_client)
    by_market = data["by_market"]
    assert "HK" in by_market, "缺少港股（HK）市场数据"
    assert "US" not in by_market and "A" not in by_market, \
        f"不应有美股或A股，实际 by_market 键：{list(by_market.keys())}"
    assert by_market["HK"]["pct"] == 100.0, \
        f"港股占比应为100%%，实际 {by_market['HK']['pct']}%%"


# ════════════════════════════════════════════════════════════════════════════
#  Test 7 – 重新同步后旧持仓应被标记为非活跃（富途卖出后不再显示）
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_stale_positions_deactivated_after_resync(db, futu_account):
    """
    重新同步时，已卖出的持仓（00005 汇丰）应被标记为 is_active=False，
    不再计入总资产。

    [Bug] _upsert_positions 内有一条无效的 SELECT，应为 UPDATE ... SET is_active=False。
    修复前：汇丰持仓保持 is_active=True → 总资产虚高。
    修复后：汇丰持仓变为 is_active=False → 总资产正确。
    """
    from services.sync_service import SyncService
    from models.portfolio import Position

    # 重新同步：只剩腾讯和港交所（汇丰已卖出）
    new_positions = [
        dict(symbol="00700", name="腾讯控股", market="HK", currency="HKD",
             quantity=1000, cost_price=380.0, current_price=450.0,
             market_value=450_000.0, unrealized_pnl=70_000.0, unrealized_pnl_pct=18.42,
             is_active=True, is_cash_equivalent=False),
        dict(symbol="00388", name="香港交易所", market="HK", currency="HKD",
             quantity=200, cost_price=250.0, current_price=290.0,
             market_value=58_000.0, unrealized_pnl=8_000.0, unrealized_pnl_pct=16.0,
             is_active=True, is_cash_equivalent=False),
    ]

    svc = SyncService(db)
    await svc._upsert_positions(futu_account.id, new_positions)

    # 验证：汇丰（00005）应被标记为非活跃
    result = await db.execute(
        select(Position).where(
            Position.account_id == futu_account.id,
            Position.symbol == "00005",
        )
    )
    hsbc = result.scalar_one_or_none()
    assert hsbc is not None, "汇丰控股持仓不应被物理删除（只应标记非活跃）"
    assert hsbc.is_active is False, (
        f"汇丰控股卖出后应为 is_active=False，实际 is_active={hsbc.is_active}"
    )

    # 验证：腾讯和港交所保持活跃
    for symbol in ("00700", "00388"):
        r = await db.execute(
            select(Position).where(
                Position.account_id == futu_account.id,
                Position.symbol == symbol,
            )
        )
        pos = r.scalar_one_or_none()
        assert pos is not None and pos.is_active is True, \
            f"{symbol} 应保持 is_active=True"
