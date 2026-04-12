"""
模拟数据 Broker — 用于开发测试，无需连接真实券商
在 .env 中设置 USE_MOCK_DATA=true 启用
"""

from typing import List, Dict, Any


MOCK_POSITIONS = [
    # 美股
    {"symbol": "AAPL", "name": "苹果", "market": "US", "currency": "USD",
     "quantity": 100, "cost_price": 165.0, "current_price": 178.5,
     "market_value": 17850.0, "unrealized_pnl": 1350.0, "unrealized_pnl_pct": 8.18,
     "broker": "mock", "pe_ratio": 28.5, "pb_ratio": 42.1, "change_pct": 1.2,
     "week_52_high": 199.62, "week_52_low": 164.08, "beta": 1.24},

    {"symbol": "NVDA", "name": "英伟达", "market": "US", "currency": "USD",
     "quantity": 50, "cost_price": 480.0, "current_price": 875.0,
     "market_value": 43750.0, "unrealized_pnl": 19750.0, "unrealized_pnl_pct": 82.29,
     "broker": "mock", "pe_ratio": 65.2, "pb_ratio": 38.7, "change_pct": 2.8,
     "week_52_high": 974.0, "week_52_low": 392.3, "beta": 1.68},

    {"symbol": "BABA", "name": "阿里巴巴", "market": "US", "currency": "USD",
     "quantity": 200, "cost_price": 90.0, "current_price": 78.3,
     "market_value": 15660.0, "unrealized_pnl": -2340.0, "unrealized_pnl_pct": -13.0,
     "broker": "mock", "pe_ratio": 12.1, "pb_ratio": 1.8, "change_pct": -0.9,
     "week_52_high": 102.5, "week_52_low": 66.63, "beta": 0.85},

    # 港股
    {"symbol": "00700", "name": "腾讯控股", "market": "HK", "currency": "HKD",
     "quantity": 400, "cost_price": 310.0, "current_price": 355.2,
     "market_value": 142080.0, "unrealized_pnl": 18080.0, "unrealized_pnl_pct": 14.58,
     "broker": "mock", "pe_ratio": 20.3, "pb_ratio": 3.5, "change_pct": 0.6,
     "week_52_high": 403.0, "week_52_low": 260.2, "beta": 0.92},

    {"symbol": "09988", "name": "阿里巴巴-W", "market": "HK", "currency": "HKD",
     "quantity": 500, "cost_price": 75.0, "current_price": 68.5,
     "market_value": 34250.0, "unrealized_pnl": -3250.0, "unrealized_pnl_pct": -8.67,
     "broker": "mock", "pe_ratio": 11.8, "pb_ratio": 1.6, "change_pct": -1.2,
     "week_52_high": 99.3, "week_52_low": 60.8, "beta": 0.88},

    # A股
    {"symbol": "600519", "name": "贵州茅台", "market": "A", "currency": "CNY",
     "quantity": 10, "cost_price": 1650.0, "current_price": 1720.0,
     "market_value": 17200.0, "unrealized_pnl": 700.0, "unrealized_pnl_pct": 4.24,
     "broker": "mock", "pe_ratio": 32.1, "pb_ratio": 11.2, "change_pct": 0.4,
     "week_52_high": 1890.0, "week_52_low": 1490.0, "beta": 0.72},

    {"symbol": "300750", "name": "宁德时代", "market": "A", "currency": "CNY",
     "quantity": 100, "cost_price": 185.0, "current_price": 172.5,
     "market_value": 17250.0, "unrealized_pnl": -1250.0, "unrealized_pnl_pct": -6.76,
     "broker": "mock", "pe_ratio": 18.5, "pb_ratio": 4.2, "change_pct": -0.8,
     "week_52_high": 235.0, "week_52_low": 130.0, "beta": 1.15},

    # 模拟货币基金（利息宝/基金余额）
    {"symbol": "_FUND", "name": "基金余额", "market": "HK", "currency": "HKD",
     "quantity": 1, "cost_price": 50000.0, "current_price": 50000.0,
     "market_value": 50000.0, "unrealized_pnl": 0.0, "unrealized_pnl_pct": 0.0,
     "broker": "mock", "is_cash_equivalent": True, "stock_type": "FUND_CASH"},

    # 模拟超短期美国国债 ETF（SGOV，等价现金）
    {"symbol": "SGOV", "name": "iShares 0-3 Month Treasury Bond ETF", "market": "US", "currency": "USD",
     "quantity": 500, "cost_price": 100.35, "current_price": 100.36,
     "market_value": 50180.0, "unrealized_pnl": 5.0, "unrealized_pnl_pct": 0.01,
     "broker": "mock", "is_cash_equivalent": True},
]

MOCK_WATCHLIST = [
    {"symbol": "MSFT", "name": "微软", "market": "US", "currency": "USD",
     "current_price": 415.0, "change_pct": 0.5, "pe_ratio": 35.2,
     "week_52_high": 468.35, "week_52_low": 309.45},
    {"symbol": "TSLA", "name": "特斯拉", "market": "US", "currency": "USD",
     "current_price": 175.0, "change_pct": -2.1, "pe_ratio": 52.4,
     "week_52_high": 299.29, "week_52_low": 138.8},
    {"symbol": "02318", "name": "中国平安", "market": "HK", "currency": "HKD",
     "current_price": 42.5, "change_pct": 0.2, "pe_ratio": 8.5, "dividend_yield": 5.2},
]


def get_mock_positions() -> Dict[str, Any]:
    return {
        "positions": MOCK_POSITIONS.copy(),
        "cash": {"amount": 12500.0, "currency": "USD"},
    }


def get_mock_watchlist() -> List[Dict[str, Any]]:
    return MOCK_WATCHLIST.copy()
