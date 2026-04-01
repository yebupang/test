from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models.portfolio import WatchList
from schemas.portfolio import WatchListCreate, WatchListUpdate, WatchListOut
from typing import List

router = APIRouter(prefix="/watchlist", tags=["关注列表"])


@router.get("/", response_model=List[WatchListOut])
async def list_watchlist(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WatchList).order_by(WatchList.market, WatchList.symbol))
    return result.scalars().all()


@router.post("/", response_model=WatchListOut)
async def add_to_watchlist(data: WatchListCreate, db: AsyncSession = Depends(get_db)):
    # 检查是否已存在
    result = await db.execute(
        select(WatchList).where(
            WatchList.symbol == data.symbol.upper(),
            WatchList.market == data.market,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(409, f"{data.symbol} 已在关注列表中")

    item = WatchList(**{**data.model_dump(), "symbol": data.symbol.upper()})
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.patch("/{item_id}", response_model=WatchListOut)
async def update_watchlist_item(
    item_id: int, data: WatchListUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(WatchList).where(WatchList.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "关注股票不存在")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(item, field, value)

    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/{item_id}")
async def remove_from_watchlist(item_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WatchList).where(WatchList.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "关注股票不存在")
    await db.delete(item)
    await db.commit()
    return {"message": "已移除"}
