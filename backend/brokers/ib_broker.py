"""
盈透证券 (Interactive Brokers) 对接模块

依赖：本地运行 TWS 或 IB Gateway
- TWS 实盘端口：7496  | 模拟盘：7497
- Gateway 实盘：4001  | 模拟盘：4002
文档：https://ib-insync.readthedocs.io/
"""

import logging
from typing import List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class IBBroker:
    """盈透证券 TWS API 封装（使用 ib_insync）"""

    def __init__(self, host: str = "127.0.0.1", port: int = 7497, client_id: int = 1):
        self.host = host
        self.port = port
        self.client_id = client_id
        self._ib = None

    def _connect(self):
        try:
            from ib_insync import IB
            self._ib = IB()
            self._ib.connect(self.host, self.port, clientId=self.client_id, timeout=10)
            logger.info(f"IB TWS 连接成功 {self.host}:{self.port}")
        except ImportError:
            raise RuntimeError("ib_insync 未安装，请运行: pip install ib_insync")
        except Exception as e:
            raise RuntimeError(
                f"IB TWS 连接失败: {e}\n"
                f"请确认 TWS/IB Gateway 已启动，并在 API 设置中启用 Socket Port {self.port}"
            )

    def _disconnect(self):
        if self._ib and self._ib.isConnected():
            self._ib.disconnect()

    def get_positions(self) -> List[Dict[str, Any]]:
        """获取盈透所有持仓"""
        self._connect()
        try:
            from ib_insync import util
            positions = self._ib.positions()
            account_values = self._ib.accountValues()

            # 获取当前市价
            contracts = [p.contract for p in positions]
            if contracts:
                tickers = self._ib.reqTickers(*contracts)
                price_map = {t.contract.symbol: t.marketPrice() for t in tickers}
            else:
                price_map = {}

            result = []
            for pos in positions:
                contract = pos.contract
                symbol = contract.symbol
                sec_type = contract.secType  # STK, OPT, FUT, ...

                if sec_type != "STK":
                    continue  # 当前只处理股票

                market = self._detect_market(contract)
                currency = contract.currency or "USD"
                avg_cost = float(pos.avgCost or 0)
                qty = float(pos.position or 0)
                cur_price = price_map.get(symbol, 0) or 0
                market_val = cur_price * qty
                pnl = (cur_price - avg_cost) * qty
                pnl_pct = ((cur_price - avg_cost) / avg_cost * 100) if avg_cost > 0 else 0

                result.append({
                    "symbol": symbol,
                    "name": contract.localSymbol or symbol,
                    "market": market,
                    "currency": currency,
                    "quantity": qty,
                    "cost_price": avg_cost,
                    "current_price": cur_price,
                    "market_value": market_val,
                    "unrealized_pnl": pnl,
                    "unrealized_pnl_pct": pnl_pct,
                    "broker": "ib",
                })

            logger.info(f"IB 持仓: {len(result)} 条")
            return result
        finally:
            self._disconnect()

    def _detect_market(self, contract) -> str:
        exchange = contract.exchange or ""
        currency = contract.currency or ""
        primary_exchange = contract.primaryExch or ""

        if currency == "HKD" or "HKEX" in exchange or "SEHK" in primary_exchange:
            return "HK"
        if currency in ("CNY", "CNH") or "SEHK" in exchange:
            return "A"
        return "US"  # 默认美股

    def get_account_summary(self) -> Dict[str, Any]:
        """获取账户资产汇总"""
        self._connect()
        try:
            values = self._ib.accountValues()
            summary = {}
            for v in values:
                if v.tag in ("NetLiquidation", "TotalCashValue", "UnrealizedPnL", "RealizedPnL"):
                    summary[v.tag] = float(v.value or 0)
            return summary
        finally:
            self._disconnect()
