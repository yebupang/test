from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models.portfolio import Account
from schemas.portfolio import AccountCreate, AccountOut
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
