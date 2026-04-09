"""
富途 OpenAPI 对接模块

依赖：本地运行 OpenD（富途牛牛 -> 设置 -> OpenAPI）
文档：https://openapi.futunn.com/futu-api-doc/
"""

import logging
from typing import List, Dict, Any, Optional

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
        self._ft = None
        self._quote_ctx = None
        self._trade_ctx_hk = None
        self._trade_ctx_us = None

    def _connect(self):
        try:
            import futu as ft
            self._ft = ft
            self._quote_ctx = ft.OpenQuoteContext(host=self.host, port=self.port)
            logger.info(f"富途 QuoteContext 连接成功 {self.host}:{self.port}")
        except ImportError:
            raise RuntimeError("futu-api 未安装，请运行: pip install futu-api")
        except Exception as e:
            raise RuntimeError(f"富途 OpenD 连接失败: {e}\n请确认 OpenD 已在本地运行")

    def _close(self):
        try:
            if self._quote_ctx:
                self._quote_ctx.close()
            if self._trade_ctx_hk:
                self._trade_ctx_hk.close()
            if self._trade_ctx_us:
                self._trade_ctx_us.close()
        except Exception:
            pass

    def _get_trade_ctx_hk(self):
        if not self._trade_ctx_hk:
            self._trade_ctx_hk = self._ft.OpenHKTradeContext(host=self.host, port=self.port)
            if self.trade_pwd:
                ret, data = self._trade_ctx_hk.unlock_trade(self.trade_pwd)
                if ret != self._ft.RET_OK:
                    logger.warning(f"港股交易解锁失败: {data}")
        return self._trade_ctx_hk

    def _get_trade_ctx_us(self):
        if not self._trade_ctx_us:
            self._trade_ctx_us = self._ft.OpenUSTradeContext(host=self.host, port=self.port)
            if self.trade_pwd:
                ret, data = self._trade_ctx_us.unlock_trade(self.trade_pwd)
                if ret != self._ft.RET_OK:
                    logger.warning(f"美股交易解锁失败: {data}")
        return self._trade_ctx_us

    def get_positions(self) -> List[Dict[str, Any]]:
        """获取所有账户持仓（港股 + 美股）"""
        self._connect()
        positions = []
        try:
            positions.extend(self._fetch_positions_hk())
            positions.extend(self._fetch_positions_us())
        finally:
            self._close()
        return positions

    def _fetch_positions_hk(self) -> List[Dict[str, Any]]:
        ctx = self._get_trade_ctx_hk()
        ret, data = ctx.position_list_query(trd_env=self._ft.TrdEnv.REAL)
        logger.info(f"港股持仓查询 ret={ret}, 行数={len(data) if ret == self._ft.RET_OK else 0}")
        if ret != self._ft.RET_OK:
            logger.warning(f"港股持仓查询失败: {data}")
            return []
        if data.empty:
            logger.info("港股持仓为空")
            return []

        logger.info(f"港股持仓列名: {list(data.columns)}")
        result = []
        for _, row in data.iterrows():
            symbol_raw = str(row.get("code", ""))
            symbol = symbol_raw.split(".")[-1] if "." in symbol_raw else symbol_raw
            qty = float(row.get("qty", 0) or 0)
            cost = float(row.get("cost_price", 0) or 0)
            market_val = float(row.get("market_val", 0) or 0)
            cur_price = market_val / qty if qty > 0 else 0
            pnl = float(row.get("pl_val", 0) or 0)
            pnl_pct = (pnl / (cost * qty) * 100) if cost > 0 and qty > 0 else 0

            result.append({
                "symbol": symbol,
                "name": str(row.get("stock_name", "")),
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
        ret, data = ctx.position_list_query(trd_env=self._ft.TrdEnv.REAL)
        logger.info(f"美股持仓查询 ret={ret}, 行数={len(data) if ret == self._ft.RET_OK else 0}")
        if ret != self._ft.RET_OK:
            logger.warning(f"美股持仓查询失败: {data}")
            return []
        if data.empty:
            logger.info("美股持仓为空")
            return []

        logger.info(f"美股持仓列名: {list(data.columns)}")
        result = []
        for _, row in data.iterrows():
            symbol_raw = str(row.get("code", ""))
            symbol = symbol_raw.split(".")[-1] if "." in symbol_raw else symbol_raw
            qty = float(row.get("qty", 0) or 0)
            cost = float(row.get("cost_price", 0) or 0)
            market_val = float(row.get("market_val", 0) or 0)
            cur_price = market_val / qty if qty > 0 else 0
            pnl = float(row.get("pl_val", 0) or 0)
            pnl_pct = (pnl / (cost * qty) * 100) if cost > 0 and qty > 0 else 0

            result.append({
                "symbol": symbol,
                "name": str(row.get("stock_name", "")),
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

    def debug_raw(self) -> Dict[str, Any]:
        """返回原始 API 数据，用于排查问题"""
        self._connect()
        result = {}
        try:
            ctx_hk = self._get_trade_ctx_hk()
            ctx_us = self._get_trade_ctx_us()

            # ── 第一步：获取账户列表 ──────────────────────────
            ret_list, acc_list = ctx_hk.get_acc_list()
            result["acc_list"] = {
                "ret": ret_list,
                "accounts": acc_list.to_dict("records") if ret_list == self._ft.RET_OK else str(acc_list),
            }

            # 从账户列表中找真实账户的 acc_id
            real_acc_id = None
            if ret_list == self._ft.RET_OK and not acc_list.empty:
                real_rows = acc_list[acc_list["trd_env"] == self._ft.TrdEnv.REAL] if "trd_env" in acc_list.columns else acc_list
                if not real_rows.empty:
                    real_acc_id = int(real_rows.iloc[0].get("acc_id", 0))

            result["detected_real_acc_id"] = real_acc_id

            # ── 第二步：用 acc_id 查持仓 ──────────────────────
            hk_kwargs = {"trd_env": self._ft.TrdEnv.REAL}
            us_kwargs = {"trd_env": self._ft.TrdEnv.REAL}
            if real_acc_id:
                hk_kwargs["acc_id"] = real_acc_id
                us_kwargs["acc_id"] = real_acc_id

            ret_hk, data_hk = ctx_hk.position_list_query(**hk_kwargs)
            result["hk"] = {
                "ret": ret_hk,
                "acc_id_used": real_acc_id,
                "columns": list(data_hk.columns) if ret_hk == self._ft.RET_OK else [],
                "rows": data_hk.to_dict("records") if ret_hk == self._ft.RET_OK else [],
                "error": str(data_hk) if ret_hk != self._ft.RET_OK else None,
            }

            ret_us, data_us = ctx_us.position_list_query(**us_kwargs)
            result["us"] = {
                "ret": ret_us,
                "acc_id_used": real_acc_id,
                "columns": list(data_us.columns) if ret_us == self._ft.RET_OK else [],
                "rows": data_us.to_dict("records") if ret_us == self._ft.RET_OK else [],
                "error": str(data_us) if ret_us != self._ft.RET_OK else None,
            }

            # ── 第三步：用 acc_id 查账户资产 ──────────────────
            acc_kwargs = {"trd_env": self._ft.TrdEnv.REAL}
            if real_acc_id:
                acc_kwargs["acc_id"] = real_acc_id
            ret_acc, acc_data = ctx_hk.accinfo_query(**acc_kwargs)
            result["accounts"] = {
                "ret": ret_acc,
                "acc_id_used": real_acc_id,
                "data": acc_data.to_dict("records") if ret_acc == self._ft.RET_OK else str(acc_data),
            }

        finally:
            self._close()
        return result

    def get_quote(self, symbols_with_market: List[tuple]) -> Dict[str, Dict]:
        """获取实时行情"""
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
