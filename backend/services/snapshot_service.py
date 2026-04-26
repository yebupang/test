"""
SnapshotService — 资金流水 + 每日资产快照

cash_flow:
  转入/转出记录，录入时按当前汇率折算 CNY，后续聚合直接用 amount_cny。

daily_snapshot:
  每日 23:00 由 APScheduler 触发，也可手动调用。
  profit_cny = total_assets_cny - net_inflow_cny
  return_pct  = profit_cny / net_inflow_cny * 100  (净流入 > 0 时)
"""

import logging
from datetime import date, datetime
from typing import List, Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete

from models.portfolio import Account, Position, CashFlow, DailySnapshot
from services.market_data import MarketDataService

logger = logging.getLogger(__name__)
mds = MarketDataService()


class SnapshotService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── 资金流水 ──────────────────────────────────────────────────────────

    async def add_cash_flow(
        self,
        account_id: int,
        kind: str,
        amount: float,
        currency: str,
        flow_date: date,
        note: Optional[str] = None,
    ) -> CashFlow:
        fx = await mds.get_exchange_rates()
        amount_cny = amount * fx.get(currency.upper(), 1.0)
        cf = CashFlow(
            account_id=account_id,
            date=flow_date,
            kind=kind,
            amount=amount,
            currency=currency.upper(),
            amount_cny=round(amount_cny, 2),
            note=note,
        )
        self.db.add(cf)
        await self.db.commit()
        await self.db.refresh(cf)
        logger.info(f"账户{account_id} {kind} {amount}{currency} ≈ {amount_cny:.2f}CNY @ {flow_date}")
        return cf

    async def get_cash_flows(self, account_id: int) -> List[CashFlow]:
        result = await self.db.execute(
            select(CashFlow)
            .where(CashFlow.account_id == account_id)
            .order_by(CashFlow.date.desc(), CashFlow.created_at.desc())
        )
        return result.scalars().all()

    async def delete_cash_flow(self, cf_id: int) -> bool:
        result = await self.db.execute(select(CashFlow).where(CashFlow.id == cf_id))
        cf = result.scalar_one_or_none()
        if not cf:
            return False
        await self.db.delete(cf)
        await self.db.commit()
        return True

    # ── 每日快照 ──────────────────────────────────────────────────────────

    async def take_daily_snapshot(self, snap_date: Optional[date] = None) -> int:
        """为所有账户 + 全局各写一行快照，已存在则覆盖（upsert）。返回写入行数。"""
        if snap_date is None:
            snap_date = date.today()

        fx = await mds.get_exchange_rates()
        accounts_result = await self.db.execute(select(Account).where(Account.is_active == True))
        accounts = accounts_result.scalars().all()

        total_assets_cny_sum = 0.0
        total_net_inflow_cny = 0.0
        written = 0

        for account in accounts:
            assets_cny = await self._compute_assets_cny(account, fx)
            net_inflow = await self._net_inflow_cny(account.id, snap_date)
            profit = round(assets_cny - net_inflow, 2)
            ret_pct = round(profit / net_inflow * 100, 4) if net_inflow > 0 else None

            await self._upsert_snapshot(
                snap_date, account.id, round(assets_cny, 2), round(net_inflow, 2), profit, ret_pct
            )
            total_assets_cny_sum += assets_cny
            total_net_inflow_cny += net_inflow
            written += 1

        # 全局合计行（account_id = None）
        total_profit = round(total_assets_cny_sum - total_net_inflow_cny, 2)
        total_ret = (
            round(total_profit / total_net_inflow_cny * 100, 4)
            if total_net_inflow_cny > 0 else None
        )
        await self._upsert_snapshot(
            snap_date, None,
            round(total_assets_cny_sum, 2),
            round(total_net_inflow_cny, 2),
            total_profit, total_ret,
        )
        written += 1

        await self.db.commit()
        logger.info(f"每日快照 {snap_date}: {written} 行（含全局合计）")
        return written

    async def get_profit_history(
        self,
        account_id: Optional[int],
        days: int = 90,
    ) -> List[DailySnapshot]:
        from datetime import timedelta
        start = date.today() - timedelta(days=days)
        query = (
            select(DailySnapshot)
            .where(DailySnapshot.date >= start)
            .order_by(DailySnapshot.date)
        )
        if account_id is None:
            query = query.where(DailySnapshot.account_id == None)
        else:
            query = query.where(DailySnapshot.account_id == account_id)
        result = await self.db.execute(query)
        return result.scalars().all()

    # ── 内部计算 ──────────────────────────────────────────────────────────

    async def _compute_assets_cny(self, account: Account, fx: Dict[str, float]) -> float:
        """股票市值（含货基）+ 现金，折算人民币。"""
        positions_result = await self.db.execute(
            select(Position).where(
                Position.account_id == account.id,
                Position.is_active == True,
            )
        )
        positions = positions_result.scalars().all()
        mv_cny = sum(
            mds.to_cny(p.market_value or 0, p.currency or "USD", fx)
            for p in positions
        )
        cash_cny = mds.to_cny(account.cash_balance or 0, account.cash_currency or "USD", fx)
        return mv_cny + cash_cny

    async def _net_inflow_cny(self, account_id: int, up_to: date) -> float:
        """截至 up_to 日（含）的累计净流入 CNY（转入 − 转出）。"""
        result = await self.db.execute(
            select(
                func.coalesce(
                    func.sum(
                        CashFlow.amount_cny
                    ),
                    0.0
                )
            ).where(
                CashFlow.account_id == account_id,
                CashFlow.date <= up_to,
            ).select_from(CashFlow)
        )
        raw = result.scalar() or 0.0

        # 分开算转入和转出
        dep_result = await self.db.execute(
            select(func.coalesce(func.sum(CashFlow.amount_cny), 0.0))
            .where(CashFlow.account_id == account_id, CashFlow.kind == "deposit", CashFlow.date <= up_to)
        )
        with_result = await self.db.execute(
            select(func.coalesce(func.sum(CashFlow.amount_cny), 0.0))
            .where(CashFlow.account_id == account_id, CashFlow.kind == "withdraw", CashFlow.date <= up_to)
        )
        deposit_total = dep_result.scalar() or 0.0
        withdraw_total = with_result.scalar() or 0.0
        return deposit_total - withdraw_total

    async def _upsert_snapshot(
        self,
        snap_date: date,
        account_id: Optional[int],
        total_assets_cny: float,
        net_inflow_cny: float,
        profit_cny: float,
        return_pct: Optional[float],
    ):
        if account_id is None:
            result = await self.db.execute(
                select(DailySnapshot).where(
                    DailySnapshot.date == snap_date,
                    DailySnapshot.account_id == None,
                )
            )
        else:
            result = await self.db.execute(
                select(DailySnapshot).where(
                    DailySnapshot.date == snap_date,
                    DailySnapshot.account_id == account_id,
                )
            )
        snap = result.scalar_one_or_none()
        if snap is None:
            snap = DailySnapshot(date=snap_date, account_id=account_id)
            self.db.add(snap)
        snap.total_assets_cny = total_assets_cny
        snap.net_inflow_cny = net_inflow_cny
        snap.profit_cny = profit_cny
        snap.return_pct = return_pct
