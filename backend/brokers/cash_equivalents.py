"""
现金等价物识别模块

将以下品种视为现金等价物，纳入现金侧计算、排除出股票仓位：
  - 货币市场基金（MMF）
  - 超短期美国国债 ETF（如 SGOV、SHV、BIL 等，久期 ≤ 1 年）
"""

from typing import Optional

# ── 超短期美国国债 ETF 白名单 ──────────────────────────────────────
# 久期 ≤ 1 年、信用风险极低，与现金风险收益特征等价
ULTRA_SHORT_TREASURY_SYMBOLS: frozenset = frozenset({
    "SGOV",   # iShares 0-3 Month Treasury Bond ETF
    "SHV",    # iShares Short Treasury Bond ETF (0-1yr)
    "BIL",    # SPDR Bloomberg 1-3 Month T-Bill ETF
    "GBIL",   # Goldman Sachs Access Treasury 0-1 Year ETF
    "CLTL",   # Invesco Treasury Collateral ETF
    "XBIL",   # US Treasury 3 Month Bill ETF
    "USFR",   # WisdomTree Floating Rate Treasury Fund
    "TFLO",   # iShares Treasury Floating Rate Bond ETF
    "ULST",   # SPDR SSgA Ultra Short Term Bond ETF
    "NEAR",   # iShares Short Maturity Bond ETF
    "ICSH",   # iShares Ultra Short-Term Bond ETF
})

# ── 名称关键词：超短期国债 ETF（用于兜底未列入白名单的同类品种）──────
_TREASURY_NAME_KEYWORDS = (
    "0-3 month treasury",
    "1-3 month treasury",
    "t-bill",
    "tbill",
    "ultra short treasury",
    "ultrashort treasury",
    "floating rate treasury",
    "treasury floating",
)


def is_ultra_short_treasury(symbol: str, name: str = "") -> bool:
    """
    判断是否为超短期美国国债 ETF（现金等价物）。

    先查白名单，再通过名称关键词兜底。
    """
    if symbol.upper() in ULTRA_SHORT_TREASURY_SYMBOLS:
        return True
    name_lower = name.lower()
    return any(kw in name_lower for kw in _TREASURY_NAME_KEYWORDS)


def is_cash_equivalent(
    symbol: str,
    name: str = "",
    stock_type: str = "",
    *,
    mmf_check_fn=None,
) -> bool:
    """
    综合判断持仓是否应计入现金侧。

    Parameters
    ----------
    symbol      : 股票/基金代码（不含市场前缀）
    name        : 证券名称
    stock_type  : 富途 SecurityType 字符串（可为空）
    mmf_check_fn: 可选的货币基金检测函数 (stock_type, name) -> bool
                  传入 FutuBroker._is_money_market_fund 即可复用现有逻辑
    """
    # 超短期国债 ETF 优先判断
    if is_ultra_short_treasury(symbol, name):
        return True
    # 货币基金（由各 broker 传入专属检测函数）
    if mmf_check_fn is not None and mmf_check_fn(stock_type, name):
        return True
    return False
