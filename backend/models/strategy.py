from sqlalchemy import Column, Integer, String, Float, Boolean, Text, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class Strategy(Base):
    """交易策略主表 — 存储用户输入的完整策略文本及解析结果"""
    __tablename__ = "strategies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)           # 策略名称，如「主策略 v1」
    description = Column(Text)                           # 用户输入的策略原文（自然语言）
    is_active = Column(Boolean, default=True)            # 当前生效的策略
    version = Column(Integer, default=1)

    # AI 解析结果（JSON）
    parsed_rules = Column(JSON)                          # 结构化规则（AI 解析后填入）

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    position_rules = relationship("PositionRule", back_populates="strategy", cascade="all, delete-orphan")
    alerts = relationship("StrategyAlert", back_populates="strategy", cascade="all, delete-orphan")


class PositionRule(Base):
    """仓位配置规则 — 五种仓位的目标比例和触发条件"""
    __tablename__ = "position_rules"

    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False)

    position_type = Column(String(20), nullable=False)   # bottom_fishing / defensive / allocation / volatile / speculative
    target_pct = Column(Float)                           # 目标比例（%），如 50.0
    min_pct = Column(Float)                              # 最小比例
    max_pct = Column(Float)                              # 最大比例

    # 触发条件（自然语言，AI 后续可解析为结构化规则）
    trigger_condition = Column(Text)                     # 如「标普500下跌超过15%时动用」
    description = Column(Text)                           # 该仓位的策略说明

    strategy = relationship("Strategy", back_populates="position_rules")


class StrategyAlert(Base):
    """策略提醒 — 合规检查生成的提醒事项"""
    __tablename__ = "strategy_alerts"

    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False)

    level = Column(String(20), nullable=False)           # info / warning / violation
    category = Column(String(50))                        # position_type / concentration / trigger
    title = Column(String(200), nullable=False)
    detail = Column(Text)
    symbol = Column(String(20))                          # 相关股票（可为空）
    is_read = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    strategy = relationship("Strategy", back_populates="alerts")
