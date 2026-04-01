"""
行情数据服务（AKShare）

AKShare 是免费的 A股/港股/美股 行情数据库
文档：https://akshare.akfan.cn/
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import pandas as pd

logger = logging.getLogger(__name__)


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
                    df = await asyncio.to_thread(
                        ak.stock_us_hist, symbol=symbol, period="daily",
                        start_date=(datetime.now() - timedelta(days=5)).strftime("%Y%m%d"),
                        end_date=datetime.now().strftime("%Y%m%d"),
                        adjust=""
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
                    df = await asyncio.to_thread(
                        ak.stock_hk_hist, symbol=symbol, period="daily",
                        start_date=(datetime.now() - timedelta(days=5)).strftime("%Y%m%d"),
                        end_date=datetime.now().strftime("%Y%m%d"),
                        adjust=""
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
                df = await asyncio.to_thread(ak.stock_zh_a_spot_em)
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

    def _safe_float(self, val) -> Optional[float]:
        try:
            v = float(str(val).replace(",", "").replace("%", ""))
            return v if v != 0 else None
        except (TypeError, ValueError):
            return None
