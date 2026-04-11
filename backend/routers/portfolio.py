from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models.portfolio import Account, Position
from schemas.portfolio import PortfolioSummary, AccountSummary, PositionOut, PositionUpdate
from services.market_data import MarketDataService
from typing import List

router = APIRouter(prefix="/portfolio", tags=["持仓组合"])


@router.get("/summary", response_model=PortfolioSummary)
async def get_portfolio_summary(db: AsyncSession = Depends(get_db)):
    """获取全仓汇总（所有账户合并，金额统一折算为人民币）"""
    accounts_result = await db.execute(select(Account).where(Account.is_active == True))
    accounts = accounts_result.scalars().all()

    # 获取实时汇率（带缓存，5 分钟刷新一次）
    mds = MarketDataService()
    fx = await mds.get_exchange_rates()  # {"USD": 7.24, "HKD": 0.93, "CNY": 1.0}

    account_summaries = []
    total_market_value = 0.0
    total_cost = 0.0
    total_pnl = 0.0
    total_market_value_cny = 0.0
    total_cost_cny = 0.0
    total_pnl_cny = 0.0
    total_cash_cny = 0.0
    by_market: dict = {}
    by_position_type: dict = {}

    for account in accounts:
        positions_result = await db.execute(
            select(Position).where(
                Position.account_id == account.id,
                Position.is_active == True,
            )
        )
        positions = positions_result.scalars().all()

        # 原币汇总
        acc_market_value = sum(p.market_value or 0 for p in positions)
        acc_cost = sum((p.cost_price or 0) * (p.quantity or 0) for p in positions)
        acc_pnl = sum(p.unrealized_pnl or 0 for p in positions)
        acc_pnl_pct = (acc_pnl / acc_cost * 100) if acc_cost > 0 else 0
        acc_cash = account.cash_balance or 0
        acc_cash_currency = account.cash_currency or "USD"
        acc_total_assets = acc_market_value + acc_cash
        acc_equity_ratio = round(acc_market_value / acc_total_assets * 100, 1) if acc_total_assets > 0 else 0

        # 各持仓折算人民币
        acc_mv_cny = sum(mds.to_cny(p.market_value or 0, p.currency or "USD", fx) for p in positions)
        acc_cost_cny = sum(mds.to_cny((p.cost_price or 0) * (p.quantity or 0), p.currency or "USD", fx) for p in positions)
        acc_pnl_cny = sum(mds.to_cny(p.unrealized_pnl or 0, p.currency or "USD", fx) for p in positions)
        acc_cash_cny = mds.to_cny(acc_cash, acc_cash_currency, fx)
        acc_total_assets_cny = acc_mv_cny + acc_cash_cny

        account_summaries.append(AccountSummary(
            account=account,
            positions=positions,
            total_market_value=acc_market_value,
            total_cost=acc_cost,
            total_pnl=acc_pnl,
            total_pnl_pct=acc_pnl_pct,
            cash_balance=acc_cash,
            cash_currency=acc_cash_currency,
            total_assets=acc_total_assets,
            equity_ratio=acc_equity_ratio,
            total_assets_cny=round(acc_total_assets_cny, 2),
        ))

        total_market_value += acc_market_value
        total_cost += acc_cost
        total_pnl += acc_pnl
        total_market_value_cny += acc_mv_cny
        total_cost_cny += acc_cost_cny
        total_pnl_cny += acc_pnl_cny
        total_cash_cny += acc_cash_cny

        # 按市场统计（折算人民币）
        for p in positions:
            market = p.market
            mv_cny = mds.to_cny(p.market_value or 0, p.currency or "USD", fx)
            pnl_cny = mds.to_cny(p.unrealized_pnl or 0, p.currency or "USD", fx)
            by_market.setdefault(market, {"market_value": 0, "market_value_cny": 0, "count": 0, "pnl": 0, "pnl_cny": 0})
            by_market[market]["market_value"] += p.market_value or 0
            by_market[market]["market_value_cny"] += mv_cny
            by_market[market]["count"] += 1
            by_market[market]["pnl"] += p.unrealized_pnl or 0
            by_market[market]["pnl_cny"] += pnl_cny

            pt = p.position_type or "unclassified"
            by_position_type.setdefault(pt, {"market_value": 0, "market_value_cny": 0, "count": 0})
            by_position_type[pt]["market_value"] += p.market_value or 0
            by_position_type[pt]["market_value_cny"] += mv_cny
            by_position_type[pt]["count"] += 1

    total_assets_cny = total_market_value_cny + total_cash_cny
    total_pnl_pct = (total_pnl_cny / total_cost_cny * 100) if total_cost_cny > 0 else 0
    total_cash = sum(a.cash_balance for a in account_summaries)
    total_assets = total_market_value + total_cash
    equity_ratio = round(total_market_value_cny / total_assets_cny * 100, 1) if total_assets_cny > 0 else 0

    # 市场分布占比用 CNY 计算
    for market, data in by_market.items():
        data["pct"] = round(data["market_value_cny"] / total_market_value_cny * 100, 2) if total_market_value_cny > 0 else 0
    for pt, data in by_position_type.items():
        data["pct"] = round(data["market_value_cny"] / total_market_value_cny * 100, 2) if total_market_value_cny > 0 else 0

    return PortfolioSummary(
        accounts=account_summaries,
        total_market_value=round(total_market_value, 2),
        total_cost=round(total_cost, 2),
        total_pnl=round(total_pnl, 2),
        total_pnl_pct=round(total_pnl_pct, 2),
        total_cash=round(total_cash, 2),
        total_assets=round(total_assets, 2),
        equity_ratio=equity_ratio,
        total_market_value_cny=round(total_market_value_cny, 2),
        total_cost_cny=round(total_cost_cny, 2),
        total_pnl_cny=round(total_pnl_cny, 2),
        total_cash_cny=round(total_cash_cny, 2),
        total_assets_cny=round(total_assets_cny, 2),
        exchange_rates=fx,
        by_market=by_market,
        by_position_type=by_position_type,
    )


@router.get("/positions", response_model=List[PositionOut])
async def list_positions(
    market: str | None = None,
    account_id: int | None = None,
    db: AsyncSession = Depends(get_db)
):
    """获取持仓列表，支持按市场/账户过滤"""
    query = select(Position).where(Position.is_active == True)
    if market:
        query = query.where(Position.market == market)
    if account_id:
        query = query.where(Position.account_id == account_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.patch("/positions/{position_id}", response_model=PositionOut)
async def update_position(
    position_id: int,
    data: PositionUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新持仓的仓位分类或备注"""
    result = await db.execute(select(Position).where(Position.id == position_id))
    pos = result.scalar_one_or_none()
    if not pos:
        raise HTTPException(404, "持仓不存在")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(pos, field, value)

    await db.commit()
    await db.refresh(pos)
    return pos
