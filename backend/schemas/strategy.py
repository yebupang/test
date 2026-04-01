from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime


# ─── PositionRule ─────────────────────────────────────────

class PositionRuleBase(BaseModel):
    position_type: str
    target_pct: Optional[float] = None
    min_pct: Optional[float] = None
    max_pct: Optional[float] = None
    trigger_condition: Optional[str] = None
    description: Optional[str] = None


class PositionRuleCreate(PositionRuleBase):
    pass


class PositionRuleOut(PositionRuleBase):
    id: int
    strategy_id: int

    class Config:
        from_attributes = True


# ─── Strategy ─────────────────────────────────────────────

class StrategyCreate(BaseModel):
    name: str = Field(..., description="策略名称")
    description: Optional[str] = Field(None, description="策略全文（自然语言）")
    position_rules: List[PositionRuleCreate] = Field(default_factory=list)


class StrategyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    position_rules: Optional[List[PositionRuleCreate]] = None


class StrategyOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    is_active: bool
    version: int
    parsed_rules: Optional[Any] = None
    position_rules: List[PositionRuleOut] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ─── StrategyAlert ────────────────────────────────────────

class AlertOut(BaseModel):
    id: int
    strategy_id: int
    level: str
    category: Optional[str]
    title: str
    detail: Optional[str]
    symbol: Optional[str]
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Compliance Check ─────────────────────────────────────

class ComplianceItem(BaseModel):
    level: str                   # info / warning / violation
    category: str
    title: str
    detail: str
    symbol: Optional[str] = None
    current_value: Optional[float] = None
    target_value: Optional[float] = None
    suggested_action: Optional[str] = None


class ComplianceReport(BaseModel):
    strategy_id: int
    strategy_name: str
    checked_at: datetime
    total_market_value: float
    items: List[ComplianceItem]
    violations: int
    warnings: int
    infos: int
    overall_status: str          # ok / warning / violation
