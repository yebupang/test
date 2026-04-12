from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from database import get_db
from models.portfolio import Account, SyncLog
from schemas.portfolio import SyncResult, SyncLogOut, CSVImportResult
from services.sync_service import SyncService
from config import get_settings
from typing import List
import asyncio

router = APIRouter(prefix="/sync", tags=["数据同步"])
settings = get_settings()


def _get_or_create_account_id_placeholder():
    """返回一个 account_id 占位，实际由前端传入"""
    return 1


@router.post("/futu/{account_id}", response_model=SyncResult)
async def sync_futu(account_id: int, db: AsyncSession = Depends(get_db)):
    """同步富途账户持仓（需要本地 OpenD 运行）"""
    svc = SyncService(db)
    try:
        result = await svc.sync_futu(account_id)
        return SyncResult(broker="futu", **result, message=result.get("message", "同步完成"))
    except Exception as e:
        raise HTTPException(503, f"富途同步失败: {e}")


@router.post("/ib/{account_id}", response_model=SyncResult)
async def sync_ib(account_id: int, db: AsyncSession = Depends(get_db)):
    """同步盈透账户持仓（需要本地 TWS/IB Gateway 运行）"""
    svc = SyncService(db)
    try:
        result = await svc.sync_ib(account_id)
        return SyncResult(broker="ib", **result, message=result.get("message", "同步完成"))
    except Exception as e:
        raise HTTPException(503, f"IB 同步失败: {e}")


@router.post("/mock/{account_id}", response_model=SyncResult)
async def sync_mock(account_id: int, db: AsyncSession = Depends(get_db)):
    """加载模拟数据（开发调试用）"""
    svc = SyncService(db)
    result = await svc.sync_mock(account_id)
    return SyncResult(broker="mock", status="success",
                      message=f"模拟数据加载完成，{result['positions_updated']} 条持仓",
                      positions_updated=result["positions_updated"])


@router.post("/csv/{account_id}", response_model=CSVImportResult)
async def sync_csv(
    account_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """上传同花顺导出的 CSV 文件，导入 A股持仓"""
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "请上传 .csv 格式文件")

    content = await file.read()
    svc = SyncService(db)
    try:
        result = await svc.sync_csv(account_id, content)
        return CSVImportResult(
            total=len(content.splitlines()),
            imported=result["positions_updated"],
            errors=result.get("errors", []),
        )
    except Exception as e:
        raise HTTPException(500, f"CSV 导入失败: {e}")


@router.post("/quotes/refresh")
async def refresh_quotes(account_id: int | None = None, db: AsyncSession = Depends(get_db)):
    """刷新所有持仓的实时行情（AKShare）"""
    svc = SyncService(db)
    count = await svc.refresh_quotes(account_id)
    return {"message": f"已刷新 {count} 条行情"}


@router.get("/logs", response_model=List[SyncLogOut])
async def get_sync_logs(limit: int = 20, db: AsyncSession = Depends(get_db)):
    """查看同步日志"""
    result = await db.execute(
        select(SyncLog).order_by(desc(SyncLog.started_at)).limit(limit)
    )
    return result.scalars().all()


@router.get("/futu/debug")
async def debug_futu():
    """调试：返回富途 API 原始数据，用于排查持仓为空问题"""
    from brokers.futu_broker import FutuBroker
    broker = FutuBroker(
        host=settings.futu_host,
        port=settings.futu_port,
        trade_pwd=settings.futu_trade_pwd,
    )
    try:
        # 富途 SDK 是同步阻塞调用，放到线程池避免卡住事件循环
        result = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, broker.debug_raw),
            timeout=15.0,
        )
        return result
    except asyncio.TimeoutError:
        raise HTTPException(504, "富途 API 超时（15s），请确认 OpenD 正在运行")
    except Exception as e:
        raise HTTPException(503, f"富途连接失败: {e}")
