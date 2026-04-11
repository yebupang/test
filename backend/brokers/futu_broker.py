"""
富途 OpenAPI 对接模块

依赖：本地运行 OpenD（富途牛牛 -> 设置 -> OpenAPI）
文档：https://openapi.futunn.com/futu-api-doc/

关键设计：
- 使用 OpenSecTradeContext（统一上下文），不再分 HK/US 两个 context
- 遍历所有 SecurityFirm 枚举值以找到当前登录的账户
- 字段：average_cost（均价）、unrealized_pl（浮动盈亏）、nominal_price（最新价）
"""

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class FutuBroker:
    def __init__(self, host: str = "127.0.0.1", port: int = 11111, trade_pwd: str = ""):
        self.host = host
        self.port = port
        self.trade_pwd = trade_pwd

    def _import_futu(self):
        try:
            import futu as ft
            return ft
        except ImportError:
            raise RuntimeError("futu-api 未安装，请运行: pip install futu-api")

    def _create_ctx(self, ft, security_firm=None, filter_market=None):
        """创建 OpenSecTradeContext，可指定 security_firm 和 filter_trdmarket"""
        kwargs: Dict[str, Any] = dict(host=self.host, port=self.port)
        if filter_market is not None:
            kwargs["filter_trdmarket"] = filter_market
        else:
            kwargs["filter_trdmarket"] = ft.TrdMarket.NONE
        if security_firm is not None:
            kwargs["security_firm"] = security_firm
        return ft.OpenSecTradeContext(**kwargs)

    def _all_security_firms(self, ft):
        """返回所有要尝试的 SecurityFirm 枚举值"""
        firms = []
        for name in ("NONE", "FUTUSECURITIES", "FUTUINC", "FUTUSG", "FUTUAU", "FUTUCA", "FUTUJP", "FUTUMY"):
            if hasattr(ft.SecurityFirm, name):
                firms.append(getattr(ft.SecurityFirm, name))
        return firms

    def _format_enum(self, val) -> str:
        if hasattr(val, "name"):
            return val.name
        return str(val)

    def _safe_float(self, val, default=0.0) -> float:
        if val is None:
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    def _safe_int(self, val, default=0) -> int:
        """大整数（18位 acc_id）必须用 int() 直接转，避免经 float 精度丢失"""
        if val is None:
            return default
        try:
            return int(val)
        except (ValueError, TypeError):
            try:
                return int(float(val))
            except (ValueError, TypeError):
                return default

    def _parse_trdmarket_auth(self, raw) -> List[str]:
        """解析 trdmarket_auth，兼容列表/字符串/枚举等多种格式"""
        if raw is None:
            return []
        if isinstance(raw, str):
            # 可能是 "[HK, US]" 或 "HK"
            cleaned = raw.strip("[]")
            return [s.strip() for s in cleaned.split(",") if s.strip()]
        if isinstance(raw, (list, tuple)):
            return [self._format_enum(m) for m in raw]
        return [str(raw)]

    def _is_real(self, trd_env_val) -> bool:
        s = self._format_enum(trd_env_val).upper()
        return s in ("REAL", "TRDENV.REAL")

    def _is_active(self, acc_status_val) -> bool:
        if acc_status_val is None:
            return True
        s = self._format_enum(acc_status_val).upper()
        return "DISABLED" not in s and "INVALID" not in s

    # ─────────────────────────────────────────────────────────
    # 公开接口
    # ─────────────────────────────────────────────────────────

    def get_positions(self) -> Dict[str, Any]:
        """获取所有真实账户持仓（港股 + 美股）和现金，在同一次连接里完成"""
        ft = self._import_futu()
        all_positions: List[Dict[str, Any]] = []
        cash_info: Dict[str, Any] = {"amount": 0.0, "currency": "HKD"}
        seen_acc_ids = set()

        for firm in self._all_security_firms(ft):
            ctx = None
            try:
                ctx = self._create_ctx(ft, security_firm=firm)
                ret, acc_list = ctx.get_acc_list()
                if ret != ft.RET_OK or acc_list is None or acc_list.empty:
                    continue

                for i in range(len(acc_list)):
                    row = acc_list.iloc[i]
                    acc_id = self._safe_int(row.get("acc_id", 0))
                    if acc_id == 0 or acc_id in seen_acc_ids:
                        continue
                    if not self._is_real(row.get("trd_env")):
                        continue
                    if not self._is_active(row.get("acc_status")):
                        logger.info(f"跳过 DISABLED 账户 acc_id={acc_id}")
                        continue

                    seen_acc_ids.add(acc_id)
                    auth = self._parse_trdmarket_auth(row.get("trdmarket_auth"))
                    logger.info(f"找到真实账户 acc_id={acc_id} trdmarket_auth={auth} firm={self._format_enum(firm)}")

                    # 查询持仓
                    ret2, pos_data = ctx.position_list_query(
                        trd_env=ft.TrdEnv.REAL, acc_id=acc_id
                    )
                    if ret2 != ft.RET_OK:
                        logger.warning(f"账户 {acc_id} 持仓查询失败: {pos_data}")
                        continue
                    if pos_data is not None and not pos_data.empty:
                        positions = self._parse_positions(pos_data)
                        logger.info(f"账户 {acc_id} 持仓 {len(positions)} 条")
                        all_positions.extend(positions)

                    # 同一连接里查现金
                    ret3, acc_data = ctx.accinfo_query(trd_env=ft.TrdEnv.REAL, acc_id=acc_id)
                    if ret3 == ft.RET_OK and acc_data is not None and not acc_data.empty:
                        r = acc_data.iloc[0]
                        cash = self._safe_float(r.get("cash", 0))
                        currency_raw = r.get("currency", "HKD")
                        currency = self._format_enum(currency_raw) if currency_raw else "HKD"
                        # currency 可能是 "Currency.HKD" 格式，取最后一段
                        if "." in str(currency):
                            currency = str(currency).split(".")[-1]
                        cash_info = {"amount": cash, "currency": currency}
                        logger.info(f"账户 {acc_id} 现金 {cash} {currency}")

            except Exception as e:
                logger.debug(f"SecurityFirm={self._format_enum(firm)} 查询跳过: {e}")
            finally:
                if ctx:
                    try:
                        ctx.close()
                    except Exception:
                        pass

        logger.info(f"富途总持仓: {len(all_positions)} 条，现金: {cash_info}")
        return {"positions": all_positions, "cash": cash_info}

    # 货币基金名称关键词（中英文，不区分大小写）
    _MMF_NAME_KEYWORDS = (
        "货币", "货基", "现金增利", "现金宝", "money market", "moneymarket",
        "cash fund", "liquid fund", "liquidity fund",
    )

    def _is_money_market_fund(self, sec_type: str, name: str) -> bool:
        """
        判断持仓是否为货币基金（应计入现金而非股票仓位）。
        判断依据：
        1. sec_type 为 FUND/MF，且名称含货基关键词；
        2. 或 sec_type 为 ETF，且名称含货基关键词（部分货基以 ETF 形式上市）。
        仅名称命中关键词也认定（兼容 sec_type 字段缺失的情况）。
        """
        name_lower = name.lower()
        name_match = any(kw in name_lower for kw in self._MMF_NAME_KEYWORDS)
        if not name_match:
            return False
        # 名称命中时，排除明显的非货基类型（如普通股票）
        st = sec_type.upper()
        if st in ("STK", "STOCK", "WARRANT", "BOND", "IDX", "INDEX", "FUTURES", "OPT"):
            return False
        return True

    def _parse_positions(self, pos_data) -> List[Dict[str, Any]]:
        """解析持仓 DataFrame，使用官方推荐字段名"""
        result = []
        for i in range(len(pos_data)):
            row = pos_data.iloc[i]
            code_raw = str(row.get("code", ""))
            # code 格式：HK.00700 / US.AAPL
            if "." in code_raw:
                market_prefix, symbol = code_raw.split(".", 1)
                market = market_prefix.upper()
            else:
                symbol = code_raw
                market = ""

            currency_map = {"HK": "HKD", "US": "USD", "CN": "CNY", "SG": "SGD"}
            currency = currency_map.get(market, "")

            name = str(row.get("stock_name", ""))
            sec_type = self._format_enum(row.get("sec_type", ""))

            qty = self._safe_float(row.get("qty", 0))
            # 官方推荐 average_cost（均价），禁止用 cost_price（摊薄成本）
            cost = self._safe_float(row.get("average_cost", 0))
            market_val = self._safe_float(row.get("market_val", 0))
            # 官方推荐 nominal_price（最新价）
            cur_price = self._safe_float(row.get("nominal_price", 0))
            if cur_price == 0 and qty > 0:
                cur_price = market_val / qty
            # 官方推荐 unrealized_pl（浮动盈亏，均价口径）
            pnl = self._safe_float(row.get("unrealized_pl", 0))
            pnl_pct = self._safe_float(row.get("pl_ratio_avg_cost", 0))

            is_cash_equiv = self._is_money_market_fund(sec_type, name)
            if is_cash_equiv:
                logger.info(f"识别为货币基金（计入现金）: {symbol} {name} sec_type={sec_type}")

            result.append({
                "symbol": symbol,
                "name": name,
                "market": market,
                "currency": currency,
                "quantity": qty,
                "cost_price": cost,
                "current_price": cur_price,
                "market_value": market_val,
                "unrealized_pnl": pnl,
                "unrealized_pnl_pct": pnl_pct,
                "broker": "futu",
                "is_cash_equivalent": is_cash_equiv,
            })
        return result

    def debug_raw(self) -> Dict[str, Any]:
        """返回原始 API 数据，用于排查问题"""
        ft = self._import_futu()
        result: Dict[str, Any] = {"firms_tried": [], "accounts": [], "positions": []}

        for firm in self._all_security_firms(ft):
            firm_name = self._format_enum(firm)
            ctx = None
            try:
                ctx = self._create_ctx(ft, security_firm=firm)
                ret, acc_list = ctx.get_acc_list()
                firm_result: Dict[str, Any] = {
                    "security_firm": firm_name,
                    "ret": ret,
                    "accounts": [],
                }

                if ret == ft.RET_OK and acc_list is not None and not acc_list.empty:
                    for i in range(len(acc_list)):
                        row = acc_list.iloc[i]
                        acc_id = self._safe_int(row.get("acc_id", 0))
                        trd_env = self._format_enum(row.get("trd_env", ""))
                        acc_status = self._format_enum(row.get("acc_status", ""))
                        auth = self._parse_trdmarket_auth(row.get("trdmarket_auth"))
                        is_real = self._is_real(trd_env)
                        is_active = self._is_active(acc_status)

                        acc_entry: Dict[str, Any] = {
                            "acc_id": acc_id,
                            "trd_env": trd_env,
                            "acc_status": acc_status,
                            "trdmarket_auth": auth,
                            "acc_role": self._format_enum(row.get("acc_role", "")),
                            "_is_real": is_real,
                            "_is_active": is_active,
                        }

                        # 尝试查询持仓
                        if is_real:
                            ret2, pos_data = ctx.position_list_query(
                                trd_env=ft.TrdEnv.REAL, acc_id=acc_id
                            )
                            acc_entry["positions_ret"] = ret2
                            if ret2 == ft.RET_OK and pos_data is not None and not pos_data.empty:
                                acc_entry["positions"] = self._parse_positions(pos_data)
                                acc_entry["positions_count"] = len(acc_entry["positions"])
                            else:
                                acc_entry["positions"] = []
                                acc_entry["positions_count"] = 0
                                if ret2 != ft.RET_OK:
                                    acc_entry["positions_error"] = str(pos_data)

                        firm_result["accounts"].append(acc_entry)

                result["firms_tried"].append(firm_result)

            except Exception as e:
                result["firms_tried"].append({"security_firm": firm_name, "error": str(e)})
            finally:
                if ctx:
                    try:
                        ctx.close()
                    except Exception:
                        pass

        return result

    def get_quote(self, symbols_with_market: List[tuple]) -> Dict[str, Dict]:
        """获取实时行情"""
        ft = self._import_futu()
        ctx = ft.OpenQuoteContext(host=self.host, port=self.port)
        try:
            codes = []
            for symbol, market in symbols_with_market:
                prefix = "US" if market == "US" else "HK"
                codes.append(f"{prefix}.{symbol}")

            ret, data = ctx.get_market_snapshot(codes)
            if ret != ft.RET_OK:
                logger.warning(f"行情查询失败: {data}")
                return {}

            result = {}
            for i in range(len(data)):
                row = data.iloc[i]
                code = str(row.get("code", ""))
                symbol = code.split(".")[-1]
                result[symbol] = {
                    "current_price": self._safe_float(row.get("last_price", 0)) or None,
                    "open_price": self._safe_float(row.get("open_price", 0)) or None,
                    "high_price": self._safe_float(row.get("high_price", 0)) or None,
                    "low_price": self._safe_float(row.get("low_price", 0)) or None,
                    "prev_close": self._safe_float(row.get("prev_close_price", 0)) or None,
                    "change_pct": self._safe_float(row.get("change_rate", 0)),
                    "volume": self._safe_float(row.get("volume", 0)),
                    "pe_ratio": self._safe_float(row.get("pe_ratio", 0)) or None,
                    "pb_ratio": self._safe_float(row.get("pb_ratio", 0)) or None,
                    "dividend_yield": self._safe_float(row.get("dividend_ttm", 0)) or None,
                    "market_cap": self._safe_float(row.get("market_val", 0)) or None,
                    "week_52_high": self._safe_float(row.get("high_price_52weeks", 0)) or None,
                    "week_52_low": self._safe_float(row.get("low_price_52weeks", 0)) or None,
                }
            return result
        finally:
            try:
                ctx.close()
            except Exception:
                pass
