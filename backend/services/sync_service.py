"""
同步服务：协调券商数据同步 + 行情更新
"""

import logging
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from models.portfolio import Account, Position, SyncLog
from services.market_data import MarketDataService
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class SyncService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.market_data = MarketDataService()

    async def sync_futu(self, account_id: int) -> Dict[str, Any]:
        """同步富途账户持仓"""
        log = SyncLog(broker="futu", status="running", started_at=datetime.utcnow())
        self.db.add(log)
        await self.db.commit()

        try:
            from brokers.futu_broker import FutuBroker
            broker = FutuBroker(
                host=settings.futu_host,
                port=settings.futu_port,
                trade_pwd=settings.futu_trade_pwd,
            )
            positions_data = broker.get_positions()
            count = await self._upsert_positions(account_id, positions_data)

            log.status = "success"
            log.positions_updated = count
            log.message = f"成功同步 {count} 条持仓"
            log.finished_at = datetime.utcnow()
            await self.db.commit()
            return {"status": "success", "positions_updated": count}

        except Exception as e:
            log.status = "failed"
            log.message = str(e)
            log.finished_at = datetime.utcnow()
            await self.db.commit()
            logger.error(f"富途同步失败: {e}")
            raise

    async def sync_ib(self, account_id: int) -> Dict[str, Any]:
        """同步盈透账户持仓"""
        log = SyncLog(broker="ib", status="running", started_at=datetime.utcnow())
        self.db.add(log)
        await self.db.commit()

        try:
            from brokers.ib_broker import IBBroker
            broker = IBBroker(
                host=settings.ib_host,
                port=settings.ib_port,
                client_id=settings.ib_client_id,
            )
            positions_data = broker.get_positions()
            count = await self._upsert_positions(account_id, positions_data)

            log.status = "success"
            log.positions_updated = count
            log.message = f"成功同步 {count} 条持仓"
            log.finished_at = datetime.utcnow()
            await self.db.commit()
            return {"status": "success", "positions_updated": count}

        except Exception as e:
            log.status = "failed"
            log.message = str(e)
            log.finished_at = datetime.utcnow()
            await self.db.commit()
            logger.error(f"IB 同步失败: {e}")
            raise

    async def sync_mock(self, account_id: int) -> Dict[str, Any]:
        """加载模拟数据（开发测试用）"""
        from brokers.mock_broker import get_mock_positions
        positions_data = get_mock_positions()
        count = await self._upsert_positions(account_id, positions_data)
        return {"status": "success", "positions_updated": count}

    async def sync_csv(self, account_id: int, csv_content: bytes) -> Dict[str, Any]:
        """从 CSV 文件同步 A股持仓"""
        log = SyncLog(broker="csv", status="running", started_at=datetime.utcnow())
        self.db.add(log)
        await self.db.commit()

        try:
            from brokers.csv_importer import parse_ths_csv
            positions_data, errors = parse_ths_csv(csv_content)
            count = await self._upsert_positions(account_id, positions_data)

            log.status = "success" if not errors else "partial"
            log.positions_updated = count
            log.message = f"导入 {count} 条，{len(errors)} 条错误: {'; '.join(errors[:3])}"
            log.finished_at = datetime.utcnow()
            await self.db.commit()
            return {"status": log.status, "positions_updated": count, "errors": errors}

        except Exception as e:
            log.status = "failed"
            log.message = str(e)
            log.finished_at = datetime.utcnow()
            await self.db.commit()
            raise

    async def refresh_quotes(self, account_id: int | None = None) -> int:
        """刷新所有持仓的实时行情"""
        query = select(Position).where(Position.is_active == True)
        if account_id:
            query = query.where(Position.account_id == account_id)

        result = await self.db.execute(query)
        positions = result.scalars().all()

        if not positions:
            return 0

        symbols_with_market = [(p.symbol, p.market) for p in positions]
        quotes = await self.market_data.get_realtime_quotes(symbols_with_market)

        updated = 0
        for pos in positions:
            q = quotes.get(pos.symbol)
            if not q:
                continue
            for field, value in q.items():
                if hasattr(pos, field) and value is not None:
                    setattr(pos, field, value)
            # 更新市值和盈亏
            if q.get("current_price") and pos.quantity:
                pos.current_price = q["current_price"]
                pos.market_value = pos.current_price * pos.quantity
                pos.unrealized_pnl = (pos.current_price - pos.cost_price) * pos.quantity
                if pos.cost_price > 0:
                    pos.unrealized_pnl_pct = (pos.current_price - pos.cost_price) / pos.cost_price * 100
            pos.updated_at = datetime.utcnow()
            updated += 1

        await self.db.commit()
        return updated

    async def _upsert_positions(self, account_id: int, positions_data: List[Dict]) -> int:
        """批量更新或插入持仓数据"""
        # 先标记该账户所有持仓为非活跃
        await self.db.execute(
            select(Position).where(Position.account_id == account_id)
        )

        count = 0
        for data in positions_data:
            symbol = data.get("symbol", "").upper()
            market = data.get("market", "")

            # 查找已有持仓
            result = await self.db.execute(
                select(Position).where(
                    Position.account_id == account_id,
                    Position.symbol == symbol,
                    Position.market == market,
                )
            )
            pos = result.scalar_one_or_none()

            if pos is None:
                pos = Position(account_id=account_id, symbol=symbol, market=market)
                self.db.add(pos)

            # 更新字段
            for field in ("name", "currency", "quantity", "cost_price", "current_price",
                          "market_value", "unrealized_pnl", "unrealized_pnl_pct",
                          "pe_ratio", "pb_ratio", "dividend_yield", "market_cap",
                          "week_52_high", "week_52_low", "beta", "change_pct"):
                if field in data and data[field] is not None:
                    setattr(pos, field, data[field])

            pos.is_active = True
            pos.updated_at = datetime.utcnow()
            count += 1

        # 更新账户最后同步时间
        result = await self.db.execute(select(Account).where(Account.id == account_id))
        account = result.scalar_one_or_none()
        if account:
            account.last_synced_at = datetime.utcnow()

        await self.db.commit()
        return count
