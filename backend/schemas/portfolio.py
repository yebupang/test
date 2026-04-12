from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ─── Account ─────────────────────────────────────────────

class AccountBase(BaseModel):
    name: str
    broker: str
    market: str
    account_id: Optional[str] = None
    currency: str = "USD"


class AccountCreate(AccountBase):
    pass


class AccountOut(AccountBase):
    id: int
    is_active: bool
    cash_balance: float = 0
    cash_currency: str = "USD"
    last_synced_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Position ─────────────────────────────────────────────

class PositionBase(BaseModel):
    symbol: str
    name: Optional[str] = None
    market: str
    currency: str = "USD"
    quantity: float = 0
    cost_price: float = 0
    current_price: float = 0
    market_value: float = 0
    unrealized_pnl: float = 0
    unrealized_pnl_pct: float = 0


class PositionOut(PositionBase):
    id: int
    account_id: int
    open_price: Optional[float] = None
    high_price: Optional[float] = None
    low_price: Optional[float] = None
    prev_close: Optional[float] = None
    change_pct: Optional[float] = None
    volume: Optional[float] = None
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    market_cap: Optional[float] = None
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None
    beta: Optional[float] = None
    position_type: Optional[str] = None
    is_cash_equivalent: bool = False
    option_right: Optional[str] = None
    option_strike: Optional[float] = None
    option_multiplier: Optional[float] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PositionUpdate(BaseModel):
    position_type: Optional[str] = None
    name: Optional[str] = None


# ─── Portfolio Summary ────────────────────────────────────

class AccountSummary(BaseModel):
    account: AccountOut
    positions: List[PositionOut]
    total_market_value: float
    total_cost: float
    total_pnl: float
    total_pnl_pct: float
    cash_balance: float = 0
    cash_currency: str = "USD"
    total_assets: float = 0            # 股票市值 + 现金（原币）
    equity_ratio: float = 0            # 仓位率（股票/总资产）
    total_market_value_cny: float = 0  # 股票市值折算人民币
    total_assets_cny: float = 0        # 总资产折算人民币
    fund_cash_cny: float = 0           # 货币基金折算人民币（已含在 total_assets_cny 中）


class PortfolioSummary(BaseModel):
    accounts: List[AccountSummary]
    total_market_value: float
    total_cost: float
    total_pnl: float
    total_pnl_pct: float
    total_cash: float = 0
    total_assets: float = 0
    equity_ratio: float = 0
    # 人民币折算
    total_market_value_cny: float = 0
    total_cost_cny: float = 0
    total_pnl_cny: float = 0
    total_cash_cny: float = 0
    total_assets_cny: float = 0
    exchange_rates: dict = {}     # {"USD": 7.24, "HKD": 0.93, "CNY": 1.0}
    by_market: dict
    by_position_type: dict


# ─── WatchList ────────────────────────────────────────────

class WatchListCreate(BaseModel):
    symbol: str
    market: str
    name: Optional[str] = None
    tags: Optional[str] = None
    note: Optional[str] = None
    target_price: Optional[float] = None
    stop_loss_price: Optional[float] = None


class WatchListUpdate(BaseModel):
    name: Optional[str] = None
    tags: Optional[str] = None
    note: Optional[str] = None
    target_price: Optional[float] = None
    stop_loss_price: Optional[float] = None


class WatchListOut(BaseModel):
    id: int
    symbol: str
    name: Optional[str] = None
    market: str
    currency: Optional[str] = None
    current_price: Optional[float] = None
    change_pct: Optional[float] = None
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None
    tags: Optional[str] = None
    note: Optional[str] = None
    target_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ─── Sync ─────────────────────────────────────────────────

class SyncResult(BaseModel):
    broker: str
    status: str
    message: str
    positions_updated: int = 0


class SyncLogOut(BaseModel):
    id: int
    broker: str
    status: str
    message: Optional[str]
    positions_updated: int
    started_at: datetime
    finished_at: Optional[datetime]

    class Config:
        from_attributes = True


# ─── CSV Import ──────────────────────────────────────────

class CSVImportResult(BaseModel):
    total: int
    imported: int
    errors: List[str] = []
