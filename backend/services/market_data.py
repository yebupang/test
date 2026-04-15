"""
行情数据服务（AKShare）

AKShare 是免费的 A股/港股/美股 行情数据库
文档：https://akshare.akfan.cn/
"""

import logging
import asyncio
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import pandas as pd

logger = logging.getLogger(__name__)

# 汇率缓存（模块级别，5 分钟 TTL）
_FX_CACHE: Dict[str, float] = {}
_FX_CACHE_TS: float = 0
_FX_CACHE_TTL = 300  # 5 分钟


class MarketDataService:
    """统一行情数据服务，底层使用 AKShare"""

    async def get_realtime_quotes(
        self, symbols_with_market: List[tuple]
    ) -> Dict[str, Dict[str, Any]]:
        """
        批量获取实时行情
        :param symbols_with_market: [(symbol, market), ...]
        :return: {symbol: {price, change_pct, pe, pb, ...}}
        """
        result = {}

        us_symbols = [(s, m) for s, m in symbols_with_market if m == "US"]
        hk_symbols = [(s, m) for s, m in symbols_with_market if m == "HK"]
        a_symbols = [(s, m) for s, m in symbols_with_market if m == "A"]

        tasks = []
        if us_symbols:
            tasks.append(self._get_us_quotes([s for s, _ in us_symbols]))
        if hk_symbols:
            tasks.append(self._get_hk_quotes([s for s, _ in hk_symbols]))
        if a_symbols:
            tasks.append(self._get_a_quotes([s for s, _ in a_symbols]))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, dict):
                result.update(r)
            elif isinstance(r, Exception):
                logger.warning(f"行情获取失败: {r}")

        return result

    async def _get_us_quotes(self, symbols: List[str]) -> Dict[str, Dict]:
        """美股行情（AKShare 实时）"""
        try:
            import akshare as ak
            result = {}
            for symbol in symbols:
                try:
                    df = await asyncio.wait_for(
                        asyncio.to_thread(
                            ak.stock_us_hist, symbol=symbol, period="daily",
                            start_date=(datetime.now() - timedelta(days=5)).strftime("%Y%m%d"),
                            end_date=datetime.now().strftime("%Y%m%d"),
                            adjust=""
                        ),
                        timeout=15.0,
                    )
                    if df is not None and not df.empty:
                        row = df.iloc[-1]
                        prev = df.iloc[-2] if len(df) > 1 else row
                        cur = float(row.get("收盘", 0) or 0)
                        prev_close = float(prev.get("收盘", 0) or 0)
                        chg = ((cur - prev_close) / prev_close * 100) if prev_close > 0 else 0
                        result[symbol] = {
                            "current_price": cur,
                            "open_price": float(row.get("开盘", 0) or 0),
                            "high_price": float(row.get("最高", 0) or 0),
                            "low_price": float(row.get("最低", 0) or 0),
                            "prev_close": prev_close,
                            "change_pct": round(chg, 2),
                            "volume": float(row.get("成交量", 0) or 0),
                        }
                except Exception as e:
                    logger.warning(f"美股 {symbol} 行情获取失败: {e}")
            return result
        except ImportError:
            logger.error("akshare 未安装，请运行: pip install akshare")
            return {}

    async def _get_hk_quotes(self, symbols: List[str]) -> Dict[str, Dict]:
        """港股行情（AKShare 实时）"""
        try:
            import akshare as ak
            result = {}
            for symbol in symbols:
                try:
                    # AKShare 港股代码格式：00700
                    df = await asyncio.wait_for(
                        asyncio.to_thread(
                            ak.stock_hk_hist, symbol=symbol, period="daily",
                            start_date=(datetime.now() - timedelta(days=5)).strftime("%Y%m%d"),
                            end_date=datetime.now().strftime("%Y%m%d"),
                            adjust=""
                        ),
                        timeout=15.0,
                    )
                    if df is not None and not df.empty:
                        row = df.iloc[-1]
                        prev = df.iloc[-2] if len(df) > 1 else row
                        cur = float(row.get("收盘", 0) or 0)
                        prev_close = float(prev.get("收盘", 0) or 0)
                        chg = ((cur - prev_close) / prev_close * 100) if prev_close > 0 else 0
                        result[symbol] = {
                            "current_price": cur,
                            "open_price": float(row.get("开盘", 0) or 0),
                            "high_price": float(row.get("最高", 0) or 0),
                            "low_price": float(row.get("最低", 0) or 0),
                            "prev_close": prev_close,
                            "change_pct": round(chg, 2),
                            "volume": float(row.get("成交量", 0) or 0),
                        }
                except Exception as e:
                    logger.warning(f"港股 {symbol} 行情获取失败: {e}")
            return result
        except ImportError:
            return {}

    async def _get_a_quotes(self, symbols: List[str]) -> Dict[str, Dict]:
        """A 股实时行情（AKShare）"""
        try:
            import akshare as ak
            result = {}
            try:
                # 批量获取 A 股实时行情
                df = await asyncio.wait_for(
                    asyncio.to_thread(ak.stock_zh_a_spot_em),
                    timeout=30.0,
                )
                if df is not None and not df.empty:
                    df["代码"] = df["代码"].astype(str).str.zfill(6)
                    for symbol in symbols:
                        sym_norm = symbol.zfill(6)
                        row_df = df[df["代码"] == sym_norm]
                        if not row_df.empty:
                            row = row_df.iloc[0]
                            result[symbol] = {
                                "current_price": float(row.get("最新价", 0) or 0),
                                "open_price": float(row.get("今开", 0) or 0),
                                "high_price": float(row.get("最高", 0) or 0),
                                "low_price": float(row.get("最低", 0) or 0),
                                "prev_close": float(row.get("昨收", 0) or 0),
                                "change_pct": float(row.get("涨跌幅", 0) or 0),
                                "volume": float(row.get("成交量", 0) or 0),
                                "turnover": float(row.get("成交额", 0) or 0),
                                "pe_ratio": float(row.get("市盈率-动态", 0) or 0) or None,
                                "pb_ratio": float(row.get("市净率", 0) or 0) or None,
                            }
            except Exception as e:
                logger.warning(f"A股行情批量获取失败: {e}")
            return result
        except ImportError:
            return {}

    async def get_stock_fundamentals(self, symbol: str, market: str) -> Dict[str, Any]:
        """获取股票基本面数据（PE/PB/股息率/52周高低）"""
        try:
            import akshare as ak
            data = {}

            if market == "A":
                try:
                    df = await asyncio.to_thread(ak.stock_individual_info_em, symbol=symbol)
                    if df is not None and not df.empty:
                        info = dict(zip(df.iloc[:, 0], df.iloc[:, 1]))
                        data["pe_ratio"] = self._safe_float(info.get("市盈率(动态)"))
                        data["pb_ratio"] = self._safe_float(info.get("市净率"))
                        data["market_cap"] = self._safe_float(info.get("总市值"))
                        data["dividend_yield"] = self._safe_float(info.get("股息率"))
                except Exception as e:
                    logger.warning(f"A股基本面 {symbol}: {e}")

            return data
        except ImportError:
            return {}

    async def get_price_history(
        self, symbol: str, market: str, days: int = 365
    ) -> List[Dict[str, Any]]:
        """获取历史K线（用于回测）"""
        try:
            import akshare as ak
            start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
            end = datetime.now().strftime("%Y%m%d")

            if market == "A":
                df = await asyncio.to_thread(
                    ak.stock_zh_a_hist, symbol=symbol, period="daily",
                    start_date=start, end_date=end, adjust="hfq"
                )
            elif market == "HK":
                df = await asyncio.to_thread(
                    ak.stock_hk_hist, symbol=symbol, period="daily",
                    start_date=start, end_date=end, adjust=""
                )
            elif market == "US":
                df = await asyncio.to_thread(
                    ak.stock_us_hist, symbol=symbol, period="daily",
                    start_date=start, end_date=end, adjust=""
                )
            else:
                return []

            if df is None or df.empty:
                return []

            result = []
            for _, row in df.iterrows():
                result.append({
                    "date": str(row.get("日期", "")),
                    "open": float(row.get("开盘", 0) or 0),
                    "high": float(row.get("最高", 0) or 0),
                    "low": float(row.get("最低", 0) or 0),
                    "close": float(row.get("收盘", 0) or 0),
                    "volume": float(row.get("成交量", 0) or 0),
                    "change_pct": float(row.get("涨跌幅", 0) or 0),
                })
            return result

        except Exception as e:
            logger.warning(f"历史数据获取失败 {symbol}: {e}")
            return []

    async def get_exchange_rates(self) -> Dict[str, float]:
        """
        获取对人民币汇率：{"USD": 6.83, "HKD": 0.88, "CNY": 1.0}
        优先从 open.er-api.com 获取实时汇率（免费、无需 key），
        失败则降级到 AKShare 中行中间价（currency_boc_safe），
        再失败尝试富途 OpenD 行情，最后使用近似值。
        结果缓存 5 分钟，避免频繁请求。
        """
        global _FX_CACHE, _FX_CACHE_TS
        if _FX_CACHE and time.time() - _FX_CACHE_TS < _FX_CACHE_TTL:
            return _FX_CACHE

        rates: Dict[str, float] = {}
        for fetcher in (self._fetch_fx_httpx, self._fetch_fx_akshare, self._fetch_fx_futu):
            try:
                rates = await fetcher()
            except Exception as e:
                logger.warning(f"{fetcher.__name__} 抛出异常: {e}")
                rates = {}
            if rates.get("USD") and rates.get("HKD"):
                break

        # 合理性校验：USD/CNY 正常范围 5.5 ~ 8.5，HKD/CNY 正常 0.7 ~ 1.1
        usd = rates.get("USD")
        hkd = rates.get("HKD")
        if not (usd and 5.5 <= usd <= 8.5):
            logger.warning(f"USD/CNY 汇率异常或缺失 ({usd})，使用近似值 6.83")
            usd = 6.83
        if not (hkd and 0.7 <= hkd <= 1.1):
            logger.warning(f"HKD/CNY 汇率异常或缺失 ({hkd})，使用近似值 0.88")
            hkd = 0.88

        result = {"CNY": 1.0, "USD": round(usd, 4), "HKD": round(hkd, 4)}
        _FX_CACHE = result
        _FX_CACHE_TS = time.time()
        logger.info(f"汇率更新: {result}")
        return result

    async def _fetch_fx_httpx(self) -> Dict[str, float]:
        """
        通过免费公共 API 获取实时汇率：
        https://open.er-api.com/v6/latest/USD
        返回 {"rates": {"CNY": 6.8278, "HKD": 7.78, ...}}
        """
        try:
            import httpx
            url = "https://open.er-api.com/v6/latest/USD"
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.get(url)
                r.raise_for_status()
                data = r.json()
            if data.get("result") != "success":
                logger.warning(f"open.er-api 返回 result != success: {data.get('result')}")
                return {}
            r_map = data.get("rates") or {}
            cny = float(r_map.get("CNY") or 0)
            hkd_usd = float(r_map.get("HKD") or 0)  # 1 USD = X HKD
            if cny <= 0 or hkd_usd <= 0:
                logger.warning(f"open.er-api 返回缺少 CNY/HKD: {r_map}")
                return {}
            result = {
                "USD": cny,              # 1 USD = cny CNY
                "HKD": cny / hkd_usd,    # 1 HKD = (cny / hkd_usd) CNY
            }
            logger.info(f"open.er-api 汇率: {result}")
            return result
        except Exception as e:
            logger.warning(f"open.er-api 汇率获取失败: {e}")
            return {}

    async def _fetch_fx_akshare(self) -> Dict[str, float]:
        """
        通过 AKShare 获取国家外汇管理局（SAFE）人民币中间价。
        函数：ak.currency_boc_safe()
        返回列包含 '日期', '美元', '港元' 等；SAFE 中间价是"每 100 外币单位对应人民币"，
        因此需要除以 100 换算为单位汇率。
        """
        try:
            import akshare as ak
        except ImportError:
            logger.warning("akshare 未安装，无法获取 SAFE 汇率")
            return {}
        try:
            df = await asyncio.wait_for(
                asyncio.to_thread(ak.currency_boc_safe),
                timeout=15.0,
            )
            if df is None or df.empty:
                logger.warning("currency_boc_safe 返回空")
                return {}
            # 取最新一行（按日期排序后的最后一行）
            df = df.sort_values(by="日期")
            row = df.iloc[-1]
            usd_100 = float(row.get("美元") or 0)
            hkd_100 = float(row.get("港元") or 0)
            if usd_100 <= 0 or hkd_100 <= 0:
                logger.warning(f"SAFE 汇率缺失: 美元={usd_100}, 港元={hkd_100}")
                return {}
            result = {
                "USD": usd_100 / 100.0,
                "HKD": hkd_100 / 100.0,
            }
            logger.info(f"SAFE 汇率({row.get('日期')}): {result}")
            return result
        except Exception as e:
            logger.warning(f"AKShare SAFE 汇率获取失败: {e}")
            return {}

    async def _fetch_fx_futu(self) -> Dict[str, float]:
        """通过富途 OpenD 行情接口获取实时汇率（最终兜底）"""
        try:
            from config import get_settings
            settings = get_settings()

            def _get():
                import futu as ft
                ctx = ft.OpenQuoteContext(host=settings.futu_host, port=settings.futu_port)
                try:
                    # 富途外汇代码格式：FX.USDCNY / FX.HKDCNY
                    ret, data = ctx.get_market_snapshot(["FX.USDCNY", "FX.HKDCNY"])
                    if ret != ft.RET_OK or data is None or data.empty:
                        return {}
                    result = {}
                    for _, row in data.iterrows():
                        code = str(row.get("code", ""))
                        price = float(row.get("last_price", 0) or 0)
                        if price > 0:
                            if "USDCNY" in code:
                                result["USD"] = price
                            elif "HKDCNY" in code:
                                result["HKD"] = price
                    return result
                finally:
                    ctx.close()

            rates = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, _get),
                timeout=8.0,
            )
            if rates:
                logger.info(f"富途汇率: {rates}")
            return rates
        except Exception as e:
            logger.warning(f"富途汇率获取失败: {e}")
            return {}

    def to_cny(self, amount: float, currency: str, rates: Dict[str, float]) -> float:
        """将金额按给定汇率换算为人民币"""
        return amount * rates.get(currency.upper(), 1.0)

    def _safe_float(self, val) -> Optional[float]:
        try:
            v = float(str(val).replace(",", "").replace("%", ""))
            return v if v != 0 else None
        except (TypeError, ValueError):
            return None
