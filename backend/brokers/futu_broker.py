"""
富途 OpenAPI 对接模块

依赖：本地运行 OpenD（富途牛牛 -> 设置 -> OpenAPI）
文档：https://openapi.futunn.com/futu-api-doc/
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class FutuBroker:
    """
    富途 OpenAPI 封装
    支持：港股、美股、A股（部分）持仓同步
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 11111, trade_pwd: str = ""):
        self.host = host
        self.port = port
        self.trade_pwd = trade_pwd
        self._quote_ctx = None
        self._trade_ctx_hk = None
        self._trade_ctx_us = None

    def _connect(self):
        try:
            import futu as ft
            self._ft = ft
            self._quote_ctx = ft.OpenQuoteContext(host=self.host, port=self.port)
            logger.info(f"富途 QuoteContext 连接成功 {self.host}:{self.port}")
            return True
        except ImportError:
            raise RuntimeError("futu-api 未安装，请运行: pip install futu-api")
        except Exception as e:
            raise RuntimeError(f"富途 OpenD 连接失败: {e}\n请确认 OpenD 已在本地运行")

    def _close(self):
        if self._quote_ctx:
            self._quote_ctx.close()
        if self._trade_ctx_hk:
            self._trade_ctx_hk.close()
        if self._trade_ctx_us:
            self._trade_ctx_us.close()

    def _get_trade_ctx_hk(self):
        if not self._trade_ctx_hk:
            self._trade_ctx_hk = self._ft.OpenHKTradeContext(host=self.host, port=self.port)
            if self.trade_pwd:
                self._trade_ctx_hk.unlock_trade(self.trade_pwd)
        return self._trade_ctx_hk

    def _get_trade_ctx_us(self):
        if not self._trade_ctx_us:
            self._trade_ctx_us = self._ft.OpenUSTradeContext(host=self.host, port=self.port)
            if self.trade_pwd:
                self._trade_ctx_us.unlock_trade(self.trade_pwd)
        return self._trade_ctx_us

    def get_positions(self) -> List[Dict[str, Any]]:
        """获取所有账户持仓（港股 + 美股）"""
        self._connect()
        positions = []

        try:
            # 港股持仓
            hk_positions = self._fetch_positions_hk()
            positions.extend(hk_positions)

            # 美股持仓
            us_positions = self._fetch_positions_us()
            positions.extend(us_positions)

        finally:
            self._close()

        return positions

    def _fetch_positions_hk(self) -> List[Dict[str, Any]]:
        ctx = self._get_trade_ctx_hk()
        ret, data = ctx.position_list_query()
        if ret != self._ft.RET_OK:
            logger.warning(f"港股持仓查询失败: {data}")
            return []

        result = []
        for _, row in data.iterrows():
            symbol_raw = row.get("code", "")
            # 富途代码格式：HK.00700 -> 00700
            symbol = symbol_raw.split(".")[-1] if "." in symbol_raw else symbol_raw
            cost = float(row.get("cost_price", 0) or 0)
            qty = float(row.get("qty", 0) or 0)
            cur_price = float(row.get("market_val", 0) or 0) / qty if qty > 0 else 0
            market_val = float(row.get("market_val", 0) or 0)
            pnl = float(row.get("pl_val", 0) or 0)
            pnl_pct = (pnl / (cost * qty) * 100) if cost > 0 and qty > 0 else 0

            result.append({
                "symbol": symbol,
                "name": row.get("stock_name", ""),
                "market": "HK",
                "currency": "HKD",
                "quantity": qty,
                "cost_price": cost,
                "current_price": cur_price,
                "market_value": market_val,
                "unrealized_pnl": pnl,
                "unrealized_pnl_pct": pnl_pct,
                "broker": "futu",
            })

        logger.info(f"富途港股持仓: {len(result)} 条")
        return result

    def _fetch_positions_us(self) -> List[Dict[str, Any]]:
        ctx = self._get_trade_ctx_us()
        ret, data = ctx.position_list_query()
        if ret != self._ft.RET_OK:
            logger.warning(f"美股持仓查询失败: {data}")
            return []

        result = []
        for _, row in data.iterrows():
            symbol_raw = row.get("code", "")
            symbol = symbol_raw.split(".")[-1] if "." in symbol_raw else symbol_raw
            cost = float(row.get("cost_price", 0) or 0)
            qty = float(row.get("qty", 0) or 0)
            market_val = float(row.get("market_val", 0) or 0)
            cur_price = market_val / qty if qty > 0 else 0
            pnl = float(row.get("pl_val", 0) or 0)
            pnl_pct = (pnl / (cost * qty) * 100) if cost > 0 and qty > 0 else 0

            result.append({
                "symbol": symbol,
                "name": row.get("stock_name", ""),
                "market": "US",
                "currency": "USD",
                "quantity": qty,
                "cost_price": cost,
                "current_price": cur_price,
                "market_value": market_val,
                "unrealized_pnl": pnl,
                "unrealized_pnl_pct": pnl_pct,
                "broker": "futu",
            })

        logger.info(f"富途美股持仓: {len(result)} 条")
        return result

    def get_quote(self, symbols_with_market: List[tuple]) -> Dict[str, Dict]:
        """
        获取实时行情
        :param symbols_with_market: [(symbol, market), ...] e.g. [("AAPL", "US"), ("00700", "HK")]
        """
        self._connect()
        try:
            ft = self._ft
            codes = []
            for symbol, market in symbols_with_market:
                prefix = "US" if market == "US" else "HK"
                codes.append(f"{prefix}.{symbol}")

            ret, data = self._quote_ctx.get_market_snapshot(codes)
            if ret != ft.RET_OK:
                logger.warning(f"行情查询失败: {data}")
                return {}

            result = {}
            for _, row in data.iterrows():
                code = row.get("code", "")
                symbol = code.split(".")[-1]
                result[symbol] = {
                    "current_price": float(row.get("last_price", 0) or 0),
                    "open_price": float(row.get("open_price", 0) or 0),
                    "high_price": float(row.get("high_price", 0) or 0),
                    "low_price": float(row.get("low_price", 0) or 0),
                    "prev_close": float(row.get("prev_close_price", 0) or 0),
                    "change_pct": float(row.get("change_rate", 0) or 0),
                    "volume": float(row.get("volume", 0) or 0),
                    "turnover": float(row.get("turnover", 0) or 0),
                    "pe_ratio": float(row.get("pe_ratio", 0) or 0) or None,
                    "pb_ratio": float(row.get("pb_ratio", 0) or 0) or None,
                    "dividend_yield": float(row.get("dividend_ttm", 0) or 0) or None,
                    "market_cap": float(row.get("market_val", 0) or 0) or None,
                    "week_52_high": float(row.get("high_price_52weeks", 0) or 0) or None,
                    "week_52_low": float(row.get("low_price_52weeks", 0) or 0) or None,
                }
            return result
        finally:
            self._close()
