"""
同步服务：协调券商数据同步 + 行情更新
"""

import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update
from models.portfolio import Account, Position, SyncLog
from services.market_data import MarketDataService
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class SyncService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.market_data = MarketDataService()

    async def _sync_broker(self, broker_name: str, account_id: int, broker_fn) -> Dict[str, Any]:
        """通用 broker 同步逻辑：调用 broker_fn() 获取 {positions, cash}，写入数据库"""
        log = SyncLog(broker=broker_name, status="running", started_at=datetime.utcnow())
        self.db.add(log)
        await self.db.commit()
        try:
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, broker_fn),
                timeout=45.0,
            )
            positions_data = result.get("positions", result) if isinstance(result, dict) else result
            cash_data = result.get("cash") if isinstance(result, dict) else None

            count = await self._upsert_positions(account_id, positions_data)
            if cash_data:
                await self._update_cash(account_id, cash_data)

            # 同步完成后自动刷新行情（Futu→AKShare），补齐 PE/PB/今日变化等字段
            try:
                await self.refresh_quotes(account_id)
            except Exception as e:
                logger.warning(f"{broker_name} 同步后行情刷新失败: {e}")

            log.status = "success"
            log.positions_updated = count
            log.message = f"成功同步 {count} 条持仓" + (f"，现金 {cash_data['amount']:.0f} {cash_data['currency']}" if cash_data else "")
            log.finished_at = datetime.utcnow()
            await self.db.commit()
            return {"status": "success", "positions_updated": count}
        except Exception as e:
            log.status = "failed"
            log.message = str(e)
            log.finished_at = datetime.utcnow()
            await self.db.commit()
            logger.error(f"{broker_name} 同步失败: {e}")
            raise

    async def sync_futu(self, account_id: int) -> Dict[str, Any]:
        """同步富途账户持仓"""
        from brokers.futu_broker import FutuBroker
        broker = FutuBroker(
            host=settings.futu_host,
            port=settings.futu_port,
            trade_pwd=settings.futu_trade_pwd,
        )
        return await self._sync_broker("futu", account_id, broker.get_positions)

    async def sync_ib(self, account_id: int) -> Dict[str, Any]:
        """同步盈透账户持仓"""
        from brokers.ib_broker import IBBroker
        broker = IBBroker(
            host=settings.ib_host,
            port=settings.ib_port,
            client_id=settings.ib_client_id,
        )
        return await self._sync_broker("ib", account_id, broker.get_positions)

    async def sync_mock(self, account_id: int) -> Dict[str, Any]:
        """加载模拟数据（开发测试用）"""
        from brokers.mock_broker import get_mock_positions
        result = get_mock_positions()
        positions_data = result.get("positions", result) if isinstance(result, dict) else result
        cash_data = result.get("cash") if isinstance(result, dict) else None
        count = await self._upsert_positions(account_id, positions_data)
        if cash_data:
            await self._update_cash(account_id, cash_data)
        return {"status": "success", "positions_updated": count}

    async def sync_csv(self, account_id: int, csv_content: bytes) -> Dict[str, Any]:
        """从 CSV 文件同步 A股持仓"""
        log = SyncLog(broker="csv", status="running", started_at=datetime.utcnow())
        self.db.add(log)
        await self.db.commit()

        try:
            from brokers.csv_importer import parse_ths_csv
            positions_data, errors = parse_ths_csv(csv_content)
            await self._deactivate_csv_positions(account_id)
            count = await self._upsert_positions(account_id, positions_data)

            try:
                await self.refresh_quotes(account_id)
            except Exception as e:
                logger.warning(f"CSV 同步后行情刷新失败: {e}")

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

    async def sync_pdf(self, account_id: int, pdf_content: bytes) -> Dict[str, Any]:
        """从华宝证券持仓申报单 PDF 同步持仓"""
        log = SyncLog(broker="csv", status="running", started_at=datetime.utcnow())
        self.db.add(log)
        await self.db.commit()

        try:
            from brokers.pdf_importer import parse_huabao_pdf
            positions_data, errors = parse_huabao_pdf(pdf_content)
            await self._deactivate_csv_positions(account_id)
            count = await self._upsert_positions(account_id, positions_data)

            try:
                await self.refresh_quotes(account_id)
            except Exception as e:
                logger.warning(f"PDF 同步后行情刷新失败: {e}")

            log.status = "success" if not errors else "partial"
            log.positions_updated = count
            log.message = f"PDF 导入 {count} 条，{len(errors)} 条错误" + (f": {'; '.join(errors[:3])}" if errors else "")
            log.finished_at = datetime.utcnow()
            await self.db.commit()
            return {"status": log.status, "positions_updated": count, "errors": errors}

        except Exception as e:
            log.status = "failed"
            log.message = str(e)
            log.finished_at = datetime.utcnow()
            await self.db.commit()
            raise

    async def sync_image(self, account_id: int, images: list) -> Dict[str, Any]:
        """从华宝证券 APP 持仓截图（PNG/JPG）同步持仓，支持多张图片"""
        log = SyncLog(broker="csv", status="running", started_at=datetime.utcnow())
        self.db.add(log)
        await self.db.commit()

        try:
            from brokers.image_importer import parse_huabao_images
            positions_data, account_summary, errors = parse_huabao_images(images)

            # 理财资产（如消费红利等股票基金）作为合成持仓写入，按股票口径计入总资产
            # 注：A 股 APP 截图汇总仅给出理财总额，无法识别具体基金，暂统一按股票（is_cash_equivalent=False）
            wealth = float(account_summary.get("wealth_management") or 0) if account_summary else 0
            if wealth > 0:
                positions_data.append({
                    "symbol": "_WEALTH",
                    "name": "理财基金",
                    "market": "A",
                    "currency": "CNY",
                    "quantity": 1,
                    "cost_price": wealth,
                    "current_price": wealth,
                    "market_value": round(wealth, 2),
                    "unrealized_pnl": 0,
                    "unrealized_pnl_pct": 0,
                    "is_cash_equivalent": False,
                })

            await self._deactivate_csv_positions(account_id)
            count = await self._upsert_positions(account_id, positions_data)

            # 同步A股现金余额（账户资产 - 证券市值 - 理财资产）
            cash_msg = ""
            if account_summary and account_summary.get("cash") is not None:
                await self._update_cash(account_id, {
                    "amount":   account_summary["cash"],
                    "currency": "CNY",
                })
                cash_msg = f"，现金 {account_summary['cash']:.2f} 元"

            # 自动刷新行情（A股 PE/PB 由 AKShare 提供；港股若同账户混合，由 Futu 兜底）
            try:
                await self.refresh_quotes(account_id)
            except Exception as e:
                logger.warning(f"截图同步后行情刷新失败: {e}")

            wealth_msg = f"，理财 {wealth:.2f} 元" if wealth > 0 else ""
            log.status = "success" if not errors else "partial"
            log.positions_updated = count
            img_count = len(images)
            log.message = (
                f"{img_count} 张截图导入 {count} 条{cash_msg}{wealth_msg}，{len(errors)} 条错误"
                + (f": {'; '.join(errors[:3])}" if errors else "")
            )
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

        # 货币基金及合成持仓（_WEALTH/_FUND 等）不走行情刷新
        positions = [
            p for p in positions
            if not p.is_cash_equivalent and not (p.symbol or "").startswith("_")
        ]
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

    async def _deactivate_csv_positions(self, account_id: int) -> None:
        """将该账户下所有持仓标为非活跃。
        A股、CSV、PDF、截图导入均使用独立账户，直接按 account_id 清空即可，
        不会影响富途/盈透账户（它们有各自的 account_id）。"""
        await self.db.execute(
            update(Position)
            .where(Position.account_id == account_id)
            .values(is_active=False)
        )

    async def _upsert_positions(self, account_id: int, positions_data: List[Dict]) -> int:
        """批量更新或插入持仓数据"""
        # 先将该账户所有持仓标为非活跃，稍后只把本次同步的持仓重新激活。
        # 这样卖出后不再出现在同步结果中的持仓会自动隐藏，不再计入总资产。
        await self.db.execute(
            update(Position)
            .where(Position.account_id == account_id)
            .values(is_active=False)
        )

        # 在循环前对 positions_data 按 (symbol, market) 去重，防止同一券商数据源重复上报同一持仓。
        # 优先保留 cost_price 非零的条目；若相同则保留 market_value 较大的。
        deduped: Dict[tuple, Dict] = {}
        for data in positions_data:
            key = (data.get("symbol", "").upper(), data.get("market", ""))
            existing = deduped.get(key)
            if existing is None:
                deduped[key] = data
            else:
                prev_cost = existing.get("cost_price") or 0
                new_cost = data.get("cost_price") or 0
                if prev_cost == 0 and new_cost != 0:
                    deduped[key] = data
                elif prev_cost == new_cost == 0:
                    if (data.get("market_value") or 0) > (existing.get("market_value") or 0):
                        deduped[key] = data
        positions_data = list(deduped.values())

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
                await self.db.flush()  # 写入 DB 使后续 SELECT 能找到，防止同批数据中重复 INSERT

            # 更新字段
            for field in ("name", "currency", "quantity", "cost_price", "current_price",
                          "market_value", "unrealized_pnl", "unrealized_pnl_pct",
                          "pe_ratio", "pb_ratio", "dividend_yield", "market_cap",
                          "week_52_high", "week_52_low", "beta", "change_pct",
                          "is_cash_equivalent",
                          "option_right", "option_strike", "option_multiplier"):
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

    async def _update_cash(self, account_id: int, cash_data: Dict[str, Any]):
        """更新账户现金余额"""
        result = await self.db.execute(select(Account).where(Account.id == account_id))
        account = result.scalar_one_or_none()
        if account:
            account.cash_balance = cash_data.get("amount", 0)
            account.cash_currency = cash_data.get("currency", "USD")
            await self.db.commit()
            logger.info(f"账户 {account_id} 现金更新: {account.cash_balance} {account.cash_currency}")
