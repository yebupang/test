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

    def _is_real_env(self, trd_env_value) -> bool:
        """判断 trd_env 是否为真实交易环境（兼容字符串和枚举两种形式）"""
        if trd_env_value is None:
            return False
        s = str(trd_env_value).upper()
        # futu-api 返回值可能是 "REAL"、"TrdEnv.REAL" 或枚举对象
        return s in ("REAL", "TRDENV.REAL", "1") or trd_env_value == self._ft.TrdEnv.REAL

    def _is_active(self, acc_status_value) -> bool:
        """判断账户是否处于可用状态"""
        if acc_status_value is None:
            return True  # 没有 status 字段时，假设可用
        s = str(acc_status_value).upper()
        return s not in ("DISABLED", "INVALID", "TRDACCSTATUS.DISABLED")

    def _has_market_auth(self, row, market: str) -> bool:
        """判断账户是否有指定市场的交易权限（兼容多种数据格式）"""
        auth = row.get("trdmarket_auth", None)
        if auth is None:
            return False
        # 无论 auth 是 list、枚举、字符串，全部转为大写字符串再匹配
        # 例如：["HK"]、[TrdMarket.HK]、"HK"、"TrdMarket.HK" 都能匹配
        return market.upper() in str(auth).upper()

    def _get_acc_info(self) -> Dict[str, int]:
        """
        获取账户列表，返回各市场对应的真实账户 acc_id。
        返回 0 表示使用 OpenD 默认账户（等同于 acc_id=0 默认值）。
        优先级：真实+可用 > 真实+DISABLED > 模拟账户 > 0（默认）
        """
        ctx_hk = self._get_trade_ctx_hk()
        ret, acc_list = ctx_hk.get_acc_list()

        result: Dict[str, int] = {"hk": 0, "us": 0}

        if ret != self._ft.RET_OK:
            logger.warning(f"get_acc_list 失败，将使用默认账户: {acc_list}")
            return result

        if acc_list is None or acc_list.empty:
            logger.warning("账户列表为空，将使用默认账户")
            return result

        logger.info(f"账户列表 ({len(acc_list)} 条):\n{acc_list.to_string()}")

        # 第一轮：真实 + 可用账户（最优先）
        for _, row in acc_list.iterrows():
            if not self._is_real_env(row.get("trd_env")):
                continue
            if not self._is_active(row.get("acc_status")):
                logger.info(
                    f"跳过 DISABLED 真实账户 acc_id={row.get('acc_id')} "
                    f"trdmarket_auth={row.get('trdmarket_auth')}"
                )
                continue
            acc_id = int(row.get("acc_id", 0))
            logger.info(f"可用真实账户 acc_id={acc_id} trdmarket_auth={row.get('trdmarket_auth')}")
            if self._has_market_auth(row, "HK") and result["hk"] == 0:
                result["hk"] = acc_id
            if self._has_market_auth(row, "US") and result["us"] == 0:
                result["us"] = acc_id

        # 第二轮：真实账户存在但 DISABLED（acc_id 仍可尝试）
        if result["hk"] == 0 or result["us"] == 0:
            for _, row in acc_list.iterrows():
                if not self._is_real_env(row.get("trd_env")):
                    continue
                acc_id = int(row.get("acc_id", 0))
                if self._has_market_auth(row, "HK") and result["hk"] == 0:
                    result["hk"] = acc_id
                    logger.info(f"使用 DISABLED 真实账户（仍尝试）HK acc_id={acc_id}")
                if self._has_market_auth(row, "US") and result["us"] == 0:
                    result["us"] = acc_id
                    logger.info(f"使用 DISABLED 真实账户（仍尝试）US acc_id={acc_id}")

        # 第三轮：模拟账户（开发调试）
        if result["hk"] == 0 or result["us"] == 0:
            logger.warning("未找到可用真实账户，尝试模拟账户")
            for _, row in acc_list.iterrows():
                acc_id = int(row.get("acc_id", 0))
                if self._has_market_auth(row, "HK") and result["hk"] == 0:
                    result["hk"] = acc_id
                    logger.info(f"降级使用模拟账户 HK acc_id={acc_id}")
                if self._has_market_auth(row, "US") and result["us"] == 0:
                    result["us"] = acc_id
                    logger.info(f"降级使用模拟账户 US acc_id={acc_id}")

        # 第四轮：任意账户（不管 trdmarket_auth）
        if result["hk"] == 0 or result["us"] == 0:
            for _, row in acc_list.iterrows():
                acc_id = int(row.get("acc_id", 0))
                if acc_id and result["hk"] == 0:
                    result["hk"] = acc_id
                    logger.info(f"无 trdmarket_auth 信息，使用任意账户 HK acc_id={acc_id}")
                if acc_id and result["us"] == 0:
                    result["us"] = acc_id
                    logger.info(f"无 trdmarket_auth 信息，使用任意账户 US acc_id={acc_id}")

        logger.info(f"最终使用账户 HK={result['hk']} US={result['us']} (0=OpenD默认)")
        return result

    def get_positions(self) -> List[Dict[str, Any]]:
        """获取所有账户持仓（港股 + 美股）"""
        self._connect()
        positions = []
        try:
            acc_info = self._get_acc_info()
            # 无论是否找到 acc_id，都尝试查询（acc_id=0 表示 OpenD 默认账户）
            positions.extend(self._fetch_positions_hk(acc_id=acc_info["hk"]))
            positions.extend(self._fetch_positions_us(acc_id=acc_info["us"]))
        finally:
            self._close()
        return positions

    def _fetch_positions_hk(self, acc_id: Optional[int] = None) -> List[Dict[str, Any]]:
        ctx = self._get_trade_ctx_hk()
        kwargs: Dict[str, Any] = {"trd_env": self._ft.TrdEnv.REAL}
        if acc_id:
            kwargs["acc_id"] = acc_id
        ret, data = ctx.position_list_query(**kwargs)
        logger.info(f"港股持仓查询 acc_id={acc_id} ret={ret}, 行数={len(data) if ret == self._ft.RET_OK else 0}")
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

    def _fetch_positions_us(self, acc_id: Optional[int] = None) -> List[Dict[str, Any]]:
        ctx = self._get_trade_ctx_us()
        kwargs: Dict[str, Any] = {"trd_env": self._ft.TrdEnv.REAL}
        if acc_id:
            kwargs["acc_id"] = acc_id
        ret, data = ctx.position_list_query(**kwargs)
        logger.info(f"美股持仓查询 acc_id={acc_id} ret={ret}, 行数={len(data) if ret == self._ft.RET_OK else 0}")
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
        result: Dict[str, Any] = {}
        try:
            ctx_hk = self._get_trade_ctx_hk()
            ctx_us = self._get_trade_ctx_us()

            # ── 第一步：获取账户列表 ──────────────────────────────────
            ret_list, acc_list = ctx_hk.get_acc_list()
            acc_records = []
            hk_acc_id = None
            us_acc_id = None

            if ret_list == self._ft.RET_OK and not acc_list.empty:
                acc_records = acc_list.to_dict("records")
                for row in acc_records:
                    is_real = self._is_real_env(row.get("trd_env"))
                    is_active = self._is_active(row.get("acc_status"))
                    has_hk = self._has_market_auth(row, "HK")
                    has_us = self._has_market_auth(row, "US")
                    acc_id = int(row.get("acc_id", 0))

                    row["_is_real"] = is_real
                    row["_is_active"] = is_active
                    row["_has_hk_auth"] = has_hk
                    row["_has_us_auth"] = has_us

                    if is_real and is_active:
                        if has_hk and hk_acc_id is None:
                            hk_acc_id = acc_id
                        if has_us and us_acc_id is None:
                            us_acc_id = acc_id

            result["acc_list"] = {
                "ret": ret_list,
                "accounts": acc_records,
                "error": str(acc_list) if ret_list != self._ft.RET_OK else None,
            }
            result["selected_hk_acc_id"] = hk_acc_id
            result["selected_us_acc_id"] = us_acc_id

            # ── 第二步：港股持仓 ──────────────────────────────────────
            if hk_acc_id:
                ret_hk, data_hk = ctx_hk.position_list_query(
                    trd_env=self._ft.TrdEnv.REAL, acc_id=hk_acc_id
                )
            else:
                ret_hk, data_hk = ctx_hk.position_list_query(trd_env=self._ft.TrdEnv.REAL)

            result["hk"] = {
                "ret": ret_hk,
                "acc_id_used": hk_acc_id,
                "columns": list(data_hk.columns) if ret_hk == self._ft.RET_OK else [],
                "rows": data_hk.to_dict("records") if ret_hk == self._ft.RET_OK else [],
                "error": str(data_hk) if ret_hk != self._ft.RET_OK else None,
            }

            # ── 第三步：美股持仓 ──────────────────────────────────────
            if us_acc_id:
                ret_us, data_us = ctx_us.position_list_query(
                    trd_env=self._ft.TrdEnv.REAL, acc_id=us_acc_id
                )
            else:
                # 不传 acc_id，让 OpenD 自动选择
                ret_us, data_us = ctx_us.position_list_query(trd_env=self._ft.TrdEnv.REAL)

            result["us"] = {
                "ret": ret_us,
                "acc_id_used": us_acc_id,
                "columns": list(data_us.columns) if ret_us == self._ft.RET_OK else [],
                "rows": data_us.to_dict("records") if ret_us == self._ft.RET_OK else [],
                "error": str(data_us) if ret_us != self._ft.RET_OK else None,
            }

            # ── 第四步：账户资产 ──────────────────────────────────────
            acc_kwargs: Dict[str, Any] = {"trd_env": self._ft.TrdEnv.REAL}
            if hk_acc_id:
                acc_kwargs["acc_id"] = hk_acc_id
            ret_acc, acc_data = ctx_hk.accinfo_query(**acc_kwargs)
            result["accinfo"] = {
                "ret": ret_acc,
                "acc_id_used": hk_acc_id,
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
