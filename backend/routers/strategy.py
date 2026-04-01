from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from datetime import datetime
from database import get_db
from models.strategy import Strategy, PositionRule, StrategyAlert
from schemas.strategy import (
    StrategyCreate, StrategyUpdate, StrategyOut,
    AlertOut, ComplianceReport,
)
from services.compliance import ComplianceEngine
from typing import List

router = APIRouter(prefix="/strategies", tags=["交易策略"])


# ─── 策略 CRUD ─────────────────────────────────────────────

@router.get("/", response_model=List[StrategyOut])
async def list_strategies(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Strategy).where(Strategy.is_active == True).order_by(Strategy.updated_at.desc())
    )
    return result.scalars().all()


@router.post("/", response_model=StrategyOut)
async def create_strategy(data: StrategyCreate, db: AsyncSession = Depends(get_db)):
    strategy = Strategy(
        name=data.name,
        description=data.description,
        is_active=True,
        version=1,
    )
    db.add(strategy)
    await db.flush()  # 获取 id

    for rule_data in data.position_rules:
        rule = PositionRule(strategy_id=strategy.id, **rule_data.model_dump())
        db.add(rule)

    await db.commit()
    await db.refresh(strategy)
    return strategy


@router.get("/{strategy_id}", response_model=StrategyOut)
async def get_strategy(strategy_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(404, "策略不存在")
    return strategy


@router.put("/{strategy_id}", response_model=StrategyOut)
async def update_strategy(
    strategy_id: int, data: StrategyUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(404, "策略不存在")

    if data.name is not None:
        strategy.name = data.name
    if data.description is not None:
        strategy.description = data.description
    if data.is_active is not None:
        strategy.is_active = data.is_active
    strategy.version += 1
    strategy.updated_at = datetime.utcnow()

    # 更新仓位规则：先删后增
    if data.position_rules is not None:
        await db.execute(delete(PositionRule).where(PositionRule.strategy_id == strategy_id))
        for rule_data in data.position_rules:
            rule = PositionRule(strategy_id=strategy_id, **rule_data.model_dump())
            db.add(rule)

    await db.commit()
    await db.refresh(strategy)
    return strategy


@router.delete("/{strategy_id}")
async def delete_strategy(strategy_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(404, "策略不存在")
    strategy.is_active = False
    await db.commit()
    return {"message": "已删除"}


# ─── 合规检查 ──────────────────────────────────────────────

@router.post("/{strategy_id}/check", response_model=ComplianceReport)
async def run_compliance_check(strategy_id: int, db: AsyncSession = Depends(get_db)):
    """执行合规检查，返回检查报告（不保存）"""
    engine = ComplianceEngine(db)
    try:
        report = await engine.run(strategy_id)
    except ValueError as e:
        raise HTTPException(404, str(e))

    # 将违规和警告持久化为 Alert
    if report.violations > 0 or report.warnings > 0:
        for item in report.items:
            if item.level in ("violation", "warning"):
                alert = StrategyAlert(
                    strategy_id=strategy_id,
                    level=item.level,
                    category=item.category,
                    title=item.title,
                    detail=item.detail,
                    symbol=item.symbol,
                )
                db.add(alert)
        await db.commit()

    return report


# ─── 提醒列表 ──────────────────────────────────────────────

@router.get("/{strategy_id}/alerts", response_model=List[AlertOut])
async def get_alerts(
    strategy_id: int,
    unread_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    query = select(StrategyAlert).where(
        StrategyAlert.strategy_id == strategy_id
    ).order_by(StrategyAlert.created_at.desc()).limit(50)
    if unread_only:
        query = query.where(StrategyAlert.is_read == False)
    result = await db.execute(query)
    return result.scalars().all()


@router.patch("/{strategy_id}/alerts/{alert_id}/read")
async def mark_alert_read(
    strategy_id: int, alert_id: int, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(StrategyAlert).where(
            StrategyAlert.id == alert_id,
            StrategyAlert.strategy_id == strategy_id,
        )
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(404, "提醒不存在")
    alert.is_read = True
    await db.commit()
    return {"message": "已标记已读"}
