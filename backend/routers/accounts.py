from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models.portfolio import Account
from schemas.portfolio import AccountCreate, AccountOut, CashFlowIn, CashFlowOut
from services.snapshot_service import SnapshotService
from typing import List

router = APIRouter(prefix="/accounts", tags=["账户管理"])


@router.get("/", response_model=List[AccountOut])
async def list_accounts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Account).where(Account.is_active == True))
    return result.scalars().all()


@router.post("/", response_model=AccountOut)
async def create_account(data: AccountCreate, db: AsyncSession = Depends(get_db)):
    account = Account(**data.model_dump())
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


@router.delete("/{account_id}")
async def delete_account(account_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Account).where(Account.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "账户不存在")
    account.is_active = False
    await db.commit()
    return {"message": "已删除"}


# ── 资金流水 ──────────────────────────────────────────────────────────────

@router.post("/{account_id}/cashflows", response_model=CashFlowOut)
async def add_cash_flow(
    account_id: int,
    data: CashFlowIn,
    db: AsyncSession = Depends(get_db),
):
    """记录账户转入或转出"""
    result = await db.execute(select(Account).where(Account.id == account_id))
    if not result.scalar_one_or_none():
        raise HTTPException(404, "账户不存在")
    svc = SnapshotService(db)
    return await svc.add_cash_flow(
        account_id=account_id,
        kind=data.kind,
        amount=data.amount,
        currency=data.currency,
        flow_date=data.date,
        note=data.note,
    )


@router.get("/{account_id}/cashflows", response_model=List[CashFlowOut])
async def get_cash_flows(account_id: int, db: AsyncSession = Depends(get_db)):
    """获取账户资金流水列表"""
    svc = SnapshotService(db)
    return await svc.get_cash_flows(account_id)


@router.delete("/{account_id}/cashflows/{cf_id}")
async def delete_cash_flow(
    account_id: int,
    cf_id: int,
    db: AsyncSession = Depends(get_db),
):
    """删除一条资金流水记录"""
    svc = SnapshotService(db)
    ok = await svc.delete_cash_flow(cf_id)
    if not ok:
        raise HTTPException(404, "记录不存在")
    return {"message": "已删除"}
