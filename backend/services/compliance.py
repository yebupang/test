"""
合规检查引擎 — 对比当前持仓与策略规则，生成提醒清单

当前版本（Phase 2）：基于仓位比例规则的规则引擎
后续版本（Phase 3）：接入 Claude API 进行自然语言策略解析和智能分析
"""

from datetime import datetime
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.portfolio import Position
from models.strategy import Strategy, PositionRule
from schemas.strategy import ComplianceItem, ComplianceReport

POSITION_TYPE_LABELS = {
    "bottom_fishing": "抄底仓",
    "defensive": "防守仓",
    "allocation": "配置仓",
    "volatile": "波动仓",
    "speculative": "投机仓",
    "unclassified": "未分类",
}


class ComplianceEngine:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def run(self, strategy_id: int) -> ComplianceReport:
        """执行合规检查，返回检查报告"""
        # 加载策略
        result = await self.db.execute(
            select(Strategy).where(Strategy.id == strategy_id)
        )
        strategy = result.scalar_one_or_none()
        if not strategy:
            raise ValueError(f"策略 {strategy_id} 不存在")

        # 加载仓位规则
        result = await self.db.execute(
            select(PositionRule).where(PositionRule.strategy_id == strategy_id)
        )
        rules = result.scalars().all()

        # 加载所有活跃持仓
        result = await self.db.execute(
            select(Position).where(Position.is_active == True)
        )
        positions = result.scalars().all()

        items: List[ComplianceItem] = []

        # ── 计算汇总数据 ─────────────────────────────────────
        total_mv = sum(p.market_value or 0 for p in positions)

        # 按仓位类型分组
        by_type: dict[str, float] = {}
        unclassified_positions = []
        for p in positions:
            pt = p.position_type or "unclassified"
            by_type[pt] = by_type.get(pt, 0) + (p.market_value or 0)
            if not p.position_type:
                unclassified_positions.append(p)

        # ── 检查1：无持仓 ─────────────────────────────────────
        if total_mv == 0:
            items.append(ComplianceItem(
                level="info",
                category="portfolio",
                title="暂无持仓数据",
                detail="请先同步券商持仓，再执行合规检查。",
            ))
            return self._build_report(strategy, total_mv, items, datetime.utcnow())

        # ── 检查2：未分类持仓 ─────────────────────────────────
        if unclassified_positions:
            symbols = ", ".join(p.symbol for p in unclassified_positions[:5])
            more = f" 等{len(unclassified_positions)}只" if len(unclassified_positions) > 5 else ""
            items.append(ComplianceItem(
                level="warning",
                category="classification",
                title=f"{len(unclassified_positions)} 只持仓未设置仓位类型",
                detail=f"{symbols}{more} 尚未分配仓位类型，无法参与策略合规检查。请在「持仓」页面为其标注仓位类型。",
            ))

        # ── 检查3：仓位比例合规 ───────────────────────────────
        for rule in rules:
            pt = rule.position_type
            label = POSITION_TYPE_LABELS.get(pt, pt)
            current_mv = by_type.get(pt, 0)
            current_pct = (current_mv / total_mv * 100) if total_mv > 0 else 0

            # 超出上限
            if rule.max_pct is not None and current_pct > rule.max_pct:
                excess = current_pct - rule.max_pct
                excess_amount = total_mv * excess / 100
                items.append(ComplianceItem(
                    level="violation",
                    category="position_type",
                    title=f"{label}超出上限 {rule.max_pct}%",
                    detail=(
                        f"当前{label}占比 {current_pct:.1f}%，策略上限 {rule.max_pct}%，"
                        f"超出 {excess:.1f}%（约 {excess_amount:,.0f} 元/美元）。"
                    ),
                    current_value=current_pct,
                    target_value=rule.max_pct,
                    suggested_action=f"建议减持 {label} 持仓至总仓位的 {rule.max_pct}% 以内",
                ))

            # 低于下限
            elif rule.min_pct is not None and current_pct < rule.min_pct and current_pct > 0:
                gap = rule.min_pct - current_pct
                items.append(ComplianceItem(
                    level="warning",
                    category="position_type",
                    title=f"{label}低于下限 {rule.min_pct}%",
                    detail=(
                        f"当前{label}占比 {current_pct:.1f}%，策略下限 {rule.min_pct}%，"
                        f"低于目标 {gap:.1f}%。"
                    ),
                    current_value=current_pct,
                    target_value=rule.min_pct,
                    suggested_action=f"建议适当增加 {label} 仓位",
                ))

            # 目标比例偏差提醒（±5%）
            elif rule.target_pct is not None:
                deviation = abs(current_pct - rule.target_pct)
                if deviation > 5:
                    direction = "高于" if current_pct > rule.target_pct else "低于"
                    items.append(ComplianceItem(
                        level="info",
                        category="position_type",
                        title=f"{label}偏离目标比例 {deviation:.1f}%",
                        detail=(
                            f"当前{label}占比 {current_pct:.1f}%，目标 {rule.target_pct}%，"
                            f"{direction}目标 {deviation:.1f}%。"
                        ),
                        current_value=current_pct,
                        target_value=rule.target_pct,
                    ))

            # 该类型无持仓但有目标比例
            if pt not in by_type and rule.target_pct and rule.target_pct > 0:
                items.append(ComplianceItem(
                    level="info",
                    category="position_type",
                    title=f"{label}当前无持仓",
                    detail=f"策略设定{label}目标比例 {rule.target_pct}%，当前无任何该类型持仓。",
                    current_value=0,
                    target_value=rule.target_pct,
                ))

        # ── 检查4：单股集中度 ─────────────────────────────────
        for p in positions:
            if total_mv > 0:
                pct = (p.market_value or 0) / total_mv * 100
                if pct > 20:
                    items.append(ComplianceItem(
                        level="warning",
                        category="concentration",
                        title=f"{p.symbol} 集中度过高 {pct:.1f}%",
                        detail=(
                            f"{p.name or p.symbol} 占总持仓 {pct:.1f}%，"
                            f"单股超过 20% 存在较高集中度风险。"
                        ),
                        symbol=p.symbol,
                        current_value=pct,
                        target_value=20.0,
                        suggested_action=f"考虑适当减持 {p.symbol} 降低集中度",
                    ))
                elif pct > 15:
                    items.append(ComplianceItem(
                        level="info",
                        category="concentration",
                        title=f"{p.symbol} 集中度较高 {pct:.1f}%",
                        detail=f"{p.name or p.symbol} 占总持仓 {pct:.1f}%，请关注集中度风险。",
                        symbol=p.symbol,
                        current_value=pct,
                    ))

        # ── 检查5：浮亏预警 ───────────────────────────────────
        for p in positions:
            pnl_pct = p.unrealized_pnl_pct or 0
            if pnl_pct < -20:
                items.append(ComplianceItem(
                    level="warning",
                    category="pnl",
                    title=f"{p.symbol} 浮亏超过 20%",
                    detail=(
                        f"{p.name or p.symbol} 当前浮亏 {pnl_pct:.1f}%，"
                        f"请检查是否符合策略中的止损规则。"
                    ),
                    symbol=p.symbol,
                    current_value=pnl_pct,
                ))

        # ── 无问题 ────────────────────────────────────────────
        if not items:
            items.append(ComplianceItem(
                level="info",
                category="portfolio",
                title="持仓符合策略规则",
                detail="当前所有检查项均通过，持仓状态与策略设定一致。",
            ))

        return self._build_report(strategy, total_mv, items, datetime.utcnow())

    def _build_report(
        self, strategy: Strategy, total_mv: float,
        items: List[ComplianceItem], checked_at: datetime
    ) -> ComplianceReport:
        violations = sum(1 for i in items if i.level == "violation")
        warnings = sum(1 for i in items if i.level == "warning")
        infos = sum(1 for i in items if i.level == "info")
        status = "violation" if violations > 0 else "warning" if warnings > 0 else "ok"

        return ComplianceReport(
            strategy_id=strategy.id,
            strategy_name=strategy.name,
            checked_at=checked_at,
            total_market_value=total_mv,
            items=items,
            violations=violations,
            warnings=warnings,
            infos=infos,
            overall_status=status,
        )
