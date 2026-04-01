"""
A股 CSV 导入模块

同花顺导出持仓步骤：
  同花顺 -> 交易 -> 持股 -> 右键导出 -> 保存为 CSV
导出字段通常包含：证券代码、证券名称、持股数量、成本价、现价、盈亏金额、盈亏比例
"""

import csv
import io
import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# 同花顺常见的列名映射（兼容不同版本导出格式）
COLUMN_ALIASES = {
    "symbol": ["证券代码", "股票代码", "代码"],
    "name": ["证券名称", "股票名称", "名称"],
    "quantity": ["持股数量", "数量", "持仓数量", "股数"],
    "cost_price": ["成本价", "成本均价", "买入均价"],
    "current_price": ["现价", "最新价", "当前价"],
    "market_value": ["市值", "持仓市值", "参考市值"],
    "unrealized_pnl": ["盈亏金额", "浮动盈亏", "参考盈亏"],
    "unrealized_pnl_pct": ["盈亏比例", "浮动盈亏比例", "收益率"],
}


def _find_column(headers: List[str], aliases: List[str]) -> str | None:
    for alias in aliases:
        if alias in headers:
            return alias
    return None


def _clean_float(val: str) -> float:
    if not val:
        return 0.0
    val = val.strip().replace(",", "").replace("%", "").replace("￥", "").replace("¥", "")
    try:
        return float(val)
    except ValueError:
        return 0.0


def parse_ths_csv(content: str | bytes) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    解析同花顺导出的持仓 CSV

    :param content: CSV 文件内容（字符串或字节）
    :return: (持仓列表, 错误信息列表)
    """
    if isinstance(content, bytes):
        # 尝试 GBK（同花顺默认），再尝试 UTF-8
        for encoding in ("gbk", "gb2312", "utf-8-sig", "utf-8"):
            try:
                content = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

    positions = []
    errors = []

    reader = csv.DictReader(io.StringIO(content))
    headers = reader.fieldnames or []

    # 找列映射
    col_map = {}
    for field, aliases in COLUMN_ALIASES.items():
        col = _find_column(headers, aliases)
        if col:
            col_map[field] = col

    if "symbol" not in col_map:
        return [], [f"找不到证券代码列，文件列名：{headers}"]

    for i, row in enumerate(reader, start=2):
        try:
            symbol = row.get(col_map.get("symbol", ""), "").strip()
            if not symbol or symbol.startswith("#"):
                continue

            # A股代码补全（同花顺有时省略交易所前缀）
            symbol = _normalize_a_symbol(symbol)

            name = row.get(col_map.get("name", ""), "").strip()
            quantity = _clean_float(row.get(col_map.get("quantity", ""), "0"))
            cost_price = _clean_float(row.get(col_map.get("cost_price", ""), "0"))
            current_price = _clean_float(row.get(col_map.get("current_price", ""), "0"))
            market_value = _clean_float(row.get(col_map.get("market_value", ""), "0"))
            unrealized_pnl = _clean_float(row.get(col_map.get("unrealized_pnl", ""), "0"))
            unrealized_pnl_pct = _clean_float(row.get(col_map.get("unrealized_pnl_pct", ""), "0"))

            if quantity <= 0:
                continue

            # 如果市值为空，自行计算
            if market_value == 0 and current_price > 0:
                market_value = current_price * quantity
            if unrealized_pnl == 0 and cost_price > 0:
                unrealized_pnl = (current_price - cost_price) * quantity
                unrealized_pnl_pct = ((current_price - cost_price) / cost_price * 100) if cost_price > 0 else 0

            positions.append({
                "symbol": symbol,
                "name": name,
                "market": "A",
                "currency": "CNY",
                "quantity": quantity,
                "cost_price": cost_price,
                "current_price": current_price,
                "market_value": market_value,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_pct": unrealized_pnl_pct,
                "broker": "csv",
            })
        except Exception as e:
            errors.append(f"第 {i} 行解析错误: {e}")

    logger.info(f"CSV 导入: {len(positions)} 条持仓，{len(errors)} 条错误")
    return positions, errors


def _normalize_a_symbol(symbol: str) -> str:
    """规范化 A 股代码（去除交易所前缀，保留6位数字）"""
    # 去除常见前缀
    for prefix in ("SH", "SZ", "sh", "sz", "600", "000", "300", "002", "688"):
        pass  # 仅做数字提取
    # 提取数字部分
    digits = "".join(c for c in symbol if c.isdigit())
    if len(digits) == 6:
        return digits
    return symbol
