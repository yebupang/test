from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey, Enum, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from database import Base


class Market(str, enum.Enum):
    US = "US"       # 美股
    HK = "HK"       # 港股
    A = "A"         # A股


class Broker(str, enum.Enum):
    FUTU = "futu"           # 富途
    IB = "ib"               # 盈透
    TONGHUASHUN = "ths"     # 同花顺（A股）
    MANUAL = "manual"       # 手动录入
    CSV = "csv"             # CSV 导入


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    broker = Column(String(20), nullable=False)
    market = Column(String(10), nullable=False)
    account_id = Column(String(100))
    currency = Column(String(10), default="USD")
    cash_balance = Column(Float, default=0)       # 账户现金余额
    cash_currency = Column(String(10), default="USD")  # 现金币种
    is_active = Column(Boolean, default=True)
    last_synced_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    positions = relationship("Position", back_populates="account", cascade="all, delete-orphan")


class Position(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)

    # 股票基本信息
    symbol = Column(String(20), nullable=False)         # 代码，如 AAPL, 00700, 600519
    name = Column(String(100))                          # 名称
    market = Column(String(10), nullable=False)         # US / HK / A
    currency = Column(String(10), default="USD")

    # 持仓数据
    quantity = Column(Float, default=0)                 # 持股数量
    cost_price = Column(Float, default=0)               # 成本均价
    current_price = Column(Float, default=0)            # 当前价格
    market_value = Column(Float, default=0)             # 市值
    unrealized_pnl = Column(Float, default=0)           # 浮动盈亏（金额）
    unrealized_pnl_pct = Column(Float, default=0)       # 浮动盈亏（百分比）

    # 行情指标（由行情服务更新）
    open_price = Column(Float)
    high_price = Column(Float)
    low_price = Column(Float)
    prev_close = Column(Float)
    change_pct = Column(Float)                          # 今日涨跌幅
    volume = Column(Float)
    turnover = Column(Float)

    # 基本面指标
    pe_ratio = Column(Float)
    pb_ratio = Column(Float)
    dividend_yield = Column(Float)
    market_cap = Column(Float)
    week_52_high = Column(Float)
    week_52_low = Column(Float)
    beta = Column(Float)

    # 仓位分类（对应策略中的五种仓位）
    position_type = Column(String(20))  # bottom_fishing / defensive / allocation / volatile / speculative

    # 资产类型标记：货币基金/现金类持仓不计入股票仓位
    is_cash_equivalent = Column(Boolean, default=False)

    # 期权专属字段（非期权持仓留 NULL）
    option_right = Column(String(1))    # "C" 或 "P"
    option_strike = Column(Float)       # 行权价
    option_multiplier = Column(Float)   # 合约乘数，美股通常为 100

    # 元数据
    is_active = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("Account", back_populates="positions")

    __table_args__ = (
        UniqueConstraint("account_id", "symbol", "market", name="uq_position_account_symbol_market"),
    )


class WatchList(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), nullable=False)
    name = Column(String(100))
    market = Column(String(10), nullable=False)
    currency = Column(String(10))

    # 当前行情
    current_price = Column(Float)
    change_pct = Column(Float)
    market_value = Column(Float)

    # 基本面
    pe_ratio = Column(Float)
    pb_ratio = Column(Float)
    dividend_yield = Column(Float)
    week_52_high = Column(Float)
    week_52_low = Column(Float)

    # 用户备注
    tags = Column(String(200))          # 逗号分隔标签
    note = Column(Text)                 # 备注
    target_price = Column(Float)        # 目标价
    stop_loss_price = Column(Float)     # 止损价

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    market = Column(String(10), nullable=False)
    date = Column(DateTime, nullable=False, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    change_pct = Column(Float)


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id = Column(Integer, primary_key=True, index=True)
    broker = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False)     # success / failed / partial
    message = Column(Text)
    positions_updated = Column(Integer, default=0)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)
