"""
盈透证券 (Interactive Brokers) 对接模块

依赖：本地运行 TWS 或 IB Gateway
- TWS 实盘端口：7496  | 模拟盘：7497
- Gateway 实盘：4001  | 模拟盘：4002
文档：https://ib-insync.readthedocs.io/
"""

import asyncio
import logging
import math
from typing import List, Dict, Any

from brokers.cash_equivalents import is_cash_equivalent

logger = logging.getLogger(__name__)


class IBBroker:
    """盈透证券 TWS API 封装（使用 ib_insync）"""

    def __init__(self, host: str = "127.0.0.1", port: int = 4001, client_id: int = 1):
        self.host = host
        self.port = port
        self.client_id = client_id
        self._ib = None
        self._loop = None

    def _connect(self):
        """
        创建标准 asyncio 事件循环并连接 IB TWS。

        uvicorn 以 uvloop 作为主线程事件循环，而 ib_insync 的 util.startLoop()
        内部调用 nest_asyncio.apply()，该库不支持 uvloop，会抛出
        "Can't patch loop of type <class 'uvloop.Loop'>" 错误。

        解决方案：在当前工作线程（executor）里显式创建标准 asyncio 事件循环，
        然后直接使用 ib_insync 的同步 API（不调用 util.startLoop()）。
        线程中新建的标准循环处于非运行状态，ib_insync 的同步包装器会通过
        loop.run_until_complete() 执行异步操作，无需 nest_asyncio。
        """
        # 显式使用标准 asyncio 策略创建事件循环，避免继承 uvloop 策略
        loop = asyncio.DefaultEventLoopPolicy().new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop

        try:
            from ib_insync import IB
        except ImportError:
            raise RuntimeError("ib_insync 未安装，请运行: pip install ib_insync")

        try:
            self._ib = IB()
            self._ib.connect(self.host, self.port, clientId=self.client_id, timeout=15)
            logger.info(f"IB TWS 连接成功 {self.host}:{self.port}")
        except Exception as e:
            raise RuntimeError(
                f"IB TWS 连接失败: {e}\n"
                f"请确认 TWS/IB Gateway 已启动，并在 API 设置中启用 Socket Port {self.port}"
            )

    def _disconnect(self):
        try:
            if self._ib and self._ib.isConnected():
                self._ib.disconnect()
        except Exception:
            pass
        finally:
            try:
                if self._loop and not self._loop.is_closed():
                    self._loop.close()
            except Exception:
                pass

    def get_positions(self) -> Dict[str, Any]:
        """获取盈透所有持仓和现金，在同一次连接里完成"""
        self._connect()
        try:
            positions = self._ib.positions()
            account_values = self._ib.accountValues()

            # 获取当前市价 — 期权用 localSymbol 作为 key，避免同标的多张期权冲突
            contracts = [p.contract for p in positions]
            if contracts:
                tickers = self._ib.reqTickers(*contracts)
                price_map = {}
                for t in tickers:
                    price = t.marketPrice()
                    if price is not None and not math.isnan(price):
                        key = t.contract.localSymbol or t.contract.symbol
                        price_map[key] = price
            else:
                price_map = {}

            result = []
            for pos in positions:
                contract = pos.contract
                if contract.secType not in ("STK", "FUND", "OPT"):
                    continue

                market = self._detect_market(contract)
                currency = contract.currency or "USD"
                avg_cost = float(pos.avgCost or 0)
                qty = float(pos.position or 0)

                if contract.secType == "OPT":
                    # 期权处理：symbol 使用 localSymbol 确保唯一性
                    symbol = contract.localSymbol or contract.symbol
                    multiplier = float(getattr(contract, "multiplier", None) or 100)
                    # 从 price_map 取权利金；休市时回退到成本权利金（avg_cost / multiplier）
                    price_key = contract.localSymbol or contract.symbol
                    cost_premium = (avg_cost / multiplier) if multiplier > 0 else avg_cost
                    option_premium = price_map.get(price_key) or cost_premium
                    # IB 的 avgCost 已含乘数（每张合约成本 = 权利金 × 乘数）
                    market_val = option_premium * multiplier * qty
                    pnl = market_val - avg_cost * qty
                    pnl_pct = (pnl / (avg_cost * qty) * 100) if avg_cost * qty != 0 else 0
                    name = self._format_option_name(contract)
                    result.append({
                        "symbol": symbol,
                        "name": name,
                        "market": market,
                        "currency": currency,
                        "quantity": qty,
                        "cost_price": avg_cost,         # 每张合约成本（含乘数）
                        "current_price": option_premium, # 权利金单价
                        "market_value": market_val,
                        "unrealized_pnl": pnl,
                        "unrealized_pnl_pct": pnl_pct,
                        "broker": "ib",
                        "is_cash_equivalent": False,
                    })
                else:
                    # 股票 / 基金
                    symbol = contract.symbol
                    price_key = contract.localSymbol or symbol
                    # 休市时 price_map 中无该 symbol，回退到均价作为当前价
                    cur_price = price_map.get(price_key) or price_map.get(symbol) or avg_cost
                    market_val = cur_price * qty
                    pnl = (cur_price - avg_cost) * qty
                    pnl_pct = ((cur_price - avg_cost) / avg_cost * 100) if avg_cost > 0 else 0
                    name = contract.localSymbol or symbol
                    result.append({
                        "symbol": symbol,
                        "name": name,
                        "market": market,
                        "currency": currency,
                        "quantity": qty,
                        "cost_price": avg_cost,
                        "current_price": cur_price,
                        "market_value": market_val,
                        "unrealized_pnl": pnl,
                        "unrealized_pnl_pct": pnl_pct,
                        "broker": "ib",
                        "is_cash_equivalent": is_cash_equivalent(symbol, name),
                    })

            # 同一连接里取现金（BASE 是折算后的账户基础货币）
            cash_amount = 0.0
            cash_currency = "USD"
            for v in account_values:
                if v.tag == "TotalCashValue" and v.currency == "BASE":
                    cash_amount = float(v.value or 0)
                    break
            if cash_amount == 0:
                for v in account_values:
                    if v.tag == "TotalCashValue":
                        cash_amount = float(v.value or 0)
                        cash_currency = v.currency or "USD"
                        break

            logger.info(f"IB 持仓: {len(result)} 条，现金: {cash_amount} {cash_currency}")
            return {"positions": result, "cash": {"amount": cash_amount, "currency": cash_currency}}
        finally:
            self._disconnect()

    def _format_option_name(self, contract) -> str:
        """将 IB 期权合约格式化为可读名称，如 'AAPL C170 2024-01-19'"""
        try:
            underlying = contract.symbol or ""
            right = getattr(contract, "right", "") or ""
            strike = getattr(contract, "strike", 0) or 0
            expiry_raw = getattr(contract, "lastTradeDateOrContractMonth", "") or ""
            if len(expiry_raw) >= 8:
                expiry = f"{expiry_raw[:4]}-{expiry_raw[4:6]}-{expiry_raw[6:8]}"
            elif len(expiry_raw) >= 6:
                expiry = f"{expiry_raw[:4]}-{expiry_raw[4:6]}"
            else:
                expiry = expiry_raw
            right_str = "C" if right.upper() == "C" else "P"
            strike_str = f"{int(strike)}" if strike == int(strike) else f"{strike:.2f}"
            return f"{underlying} {right_str}{strike_str} {expiry}"
        except Exception:
            return contract.localSymbol or contract.symbol or "OPT"

    def _detect_market(self, contract) -> str:
        exchange = getattr(contract, "exchange", "") or ""
        currency = getattr(contract, "currency", "") or ""
        # ib_insync 0.9.x 使用 primaryExchange（旧版为 primaryExch）
        primary_exchange = (
            getattr(contract, "primaryExchange", "")
            or getattr(contract, "primaryExch", "")
            or ""
        )

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
