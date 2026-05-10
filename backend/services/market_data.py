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
        """美股行情：yfinance 优先（含 PE/PB/change），Futu 兜底，AKShare 最后"""
        result = await self._get_us_quotes_yfinance(symbols)
        missing = [s for s in symbols if s not in result or not result[s].get("current_price")]
        if missing:
            futu_result = await self._get_quotes_futu([(s, "US") for s in missing])
            for s, q in futu_result.items():
                result.setdefault(s, {}).update({k: v for k, v in q.items() if v is not None})
        missing2 = [s for s in symbols if s not in result or not result[s].get("current_price")]
        if missing2:
            ak_result = await self._get_us_quotes_akshare(missing2)
            for s, q in ak_result.items():
                result.setdefault(s, {}).update({k: v for k, v in q.items() if v is not None})
        return result

    async def _get_us_quotes_yfinance(self, symbols: List[str]) -> Dict[str, Dict]:
        """通过 yfinance 批量获取美股行情（含 PE/PB）"""
        try:
            import yfinance as yf

            def _fetch():
                out: Dict[str, Dict] = {}
                for sym in symbols:
                    try:
                        t = yf.Ticker(sym)
                        info = t.info or {}
                        cur = info.get("currentPrice") or info.get("regularMarketPrice") or 0
                        prev = info.get("previousClose") or info.get("regularMarketPreviousClose") or 0
                        chg = info.get("regularMarketChangePercent") or (
                            round((cur - prev) / prev * 100, 2) if prev else 0
                        )
                        pe = info.get("trailingPE") or info.get("forwardPE") or 0
                        pb = info.get("priceToBook") or 0
                        mc = info.get("marketCap") or 0
                        div = info.get("dividendYield") or 0
                        h52 = info.get("fiftyTwoWeekHigh") or 0
                        l52 = info.get("fiftyTwoWeekLow") or 0
                        if cur and cur > 0:
                            out[sym] = {
                                "current_price": float(cur),
                                "prev_close": float(prev) or None,
                                "change_pct": float(chg) if chg else None,
                                "pe_ratio": float(pe) if pe and pe > 0 else None,
                                "pb_ratio": float(pb) if pb and pb > 0 else None,
                                "market_cap": float(mc) if mc else None,
                                "dividend_yield": float(div * 100) if div else None,
                                "week_52_high": float(h52) if h52 else None,
                                "week_52_low": float(l52) if l52 else None,
                            }
                    except Exception as e:
                        logger.warning(f"yfinance {sym}: {e}")
                return out

            return await asyncio.wait_for(asyncio.to_thread(_fetch), timeout=20.0)
        except ImportError:
            logger.warning("yfinance 未安装，跳过（运行 pip install yfinance）")
            return {}
        except Exception as e:
            logger.warning(f"yfinance 批量行情失败: {e}")
            return {}

    async def _get_hk_quotes(self, symbols: List[str]) -> Dict[str, Dict]:
        """港股行情：Futu OpenD 优先（含 PE/PB/change），AKShare 兜底"""
        result = await self._get_quotes_futu([(s, "HK") for s in symbols])
        missing = [s for s in symbols if s not in result or not result[s].get("current_price")]
        if missing:
            ak_result = await self._get_hk_quotes_akshare(missing)
            for s, q in ak_result.items():
                result.setdefault(s, {}).update({k: v for k, v in q.items() if v is not None})
        return result



    async def _get_quotes_futu(self, symbols_with_market: List[tuple]) -> Dict[str, Dict]:
        """通过富途 OpenD 获取 US/HK 行情（含 PE/PB、change_pct、52w 高低）"""
        if not symbols_with_market:
            return {}
        try:
            from config import get_settings
            settings = get_settings()

            def _fetch():
                import futu as ft
                ctx = ft.OpenQuoteContext(host=settings.futu_host, port=settings.futu_port)
                try:
                    codes = []
                    for sym, market in symbols_with_market:
                        prefix = "US" if market == "US" else "HK"
                        codes.append(f"{prefix}.{sym}")
                    ret, data = ctx.get_market_snapshot(codes)
                    if ret != ft.RET_OK or data is None or data.empty:
                        return {}
                    out: Dict[str, Dict] = {}
                    for i in range(len(data)):
                        row = data.iloc[i]
                        code = str(row.get("code", ""))
                        symbol = code.split(".")[-1]
                        out[symbol] = {
                            "current_price": self._safe_float(row.get("last_price")),
                            "open_price":    self._safe_float(row.get("open_price")),
                            "high_price":    self._safe_float(row.get("high_price")),
                            "low_price":     self._safe_float(row.get("low_price")),
                            "prev_close":    self._safe_float(row.get("prev_close_price")),
                            "change_pct":    self._safe_float(row.get("change_rate")),
                            "volume":        self._safe_float(row.get("volume")),
                            "pe_ratio":      self._safe_float(row.get("pe_ratio")),
                            "pb_ratio":      self._safe_float(row.get("pb_ratio")),
                            "dividend_yield": self._safe_float(row.get("dividend_ratio_ttm"))
                                              or self._safe_float(row.get("dividend_ttm")),
                            "market_cap":    self._safe_float(row.get("total_market_val"))
                                              or self._safe_float(row.get("market_val")),
                            "week_52_high":  self._safe_float(row.get("high_price_52weeks")),
                            "week_52_low":   self._safe_float(row.get("low_price_52weeks")),
                        }
                    return out
                finally:
                    ctx.close()

            return await asyncio.wait_for(
                asyncio.to_thread(_fetch),
                timeout=12.0,
            )
        except Exception as e:
            logger.warning(f"富途行情获取失败: {e}")
            return {}

    async def _get_us_quotes_akshare(self, symbols: List[str]) -> Dict[str, Dict]:
        """美股行情兜底（AKShare 历史日线）"""
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

    async def _get_hk_quotes_akshare(self, symbols: List[str]) -> Dict[str, Dict]:
        """港股行情兜底（AKShare 历史日线）"""
        try:
            import akshare as ak
            result = {}
            for symbol in symbols:
                try:
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
        for fetcher in (self._fetch_fx_futu, self._fetch_fx_httpx):
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
