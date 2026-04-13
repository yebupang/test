"""
华宝证券「上个交易日持仓申报单」PDF 解析器

PDF 结构（两个表格，均含表格线）：
  股票持仓：持有人姓名 | 股票代码 | 股票名称 | 前一交易日持股数量 | 前一交易日市值（万元）| ...
  基金持仓：持有人姓名 | 基金代码 | 基金简称 | 前一交易日基金份额 | 前一交易日净值（万元）

市值/净值单位均为人民币万元；PDF 不含成本价（导入后记为 0）。

依赖：pip install pymupdf
"""

import io
import logging
import re
from typing import List, Dict, Any, Tuple

from brokers.cash_equivalents import is_cash_equivalent

logger = logging.getLogger(__name__)

# ── 列名候选（子串匹配，兼容不同写法）────────────────────────────────────
_STOCK_CODE_KEYS = ["股票代码", "证券代码"]
_STOCK_NAME_KEYS = ["股票名称", "证券名称"]
_STOCK_QTY_KEYS  = ["持股数量"]
_STOCK_MV_KEYS   = ["市值"]       # 含"市值"即命中

_FUND_CODE_KEYS  = ["基金代码"]
_FUND_NAME_KEYS  = ["基金简称", "基金名称"]
_FUND_QTY_KEYS   = ["基金份额", "份额"]
_FUND_NAV_KEYS   = ["净值"]       # 含"净值"即命中


def parse_huabao_pdf(content: bytes) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    解析华宝证券持仓申报单 PDF。

    :param content: PDF 文件字节内容
    :return: (持仓列表, 错误信息列表)
    """
    try:
        import fitz
    except ImportError:
        raise RuntimeError("PyMuPDF 未安装，请运行: pip install pymupdf")

    positions: List[Dict[str, Any]] = []
    errors: List[str] = []

    try:
        doc = fitz.open(stream=content, filetype="pdf")
        for page_num, page in enumerate(doc, start=1):
            try:
                _parse_page(page, positions, errors)
            except Exception as e:
                errors.append(f"第 {page_num} 页解析失败: {e}")
                logger.exception(f"PDF 第 {page_num} 页解析异常")
        doc.close()
    except Exception as e:
        errors.append(f"PDF 打开失败: {e}")
        return [], errors

    if not positions and not errors:
        errors.append("未解析到任何持仓数据，请确认为华宝证券持仓申报单格式")

    logger.info(f"华宝 PDF 导入: {len(positions)} 条持仓，{len(errors)} 条错误")
    return positions, errors


def _parse_page(page, positions: List, errors: List):
    """优先用表格检测，失败则回退到文本解析"""
    tab_finder = page.find_tables()
    if tab_finder.tables:
        logger.debug(f"find_tables 找到 {len(tab_finder.tables)} 个表格")
        for tab in tab_finder.tables:
            rows = tab.extract()
            _parse_table(rows, positions, errors)
    else:
        # 回退：从纯文字中按行重建表格结构
        logger.debug("未找到表格线，回退到文本解析")
        _parse_text_fallback(page.get_text(), positions, errors)


# ── 表格解析 ─────────────────────────────────────────────────────────────

def _parse_table(rows: List[List], positions: List, errors: List):
    """判断表类型（股票/基金）并分发解析"""
    if not rows or len(rows) < 2:
        return
    headers = [_cell(c) for c in rows[0]]
    if not any(headers):
        return

    logger.debug(f"表头: {headers}")

    is_stock = (_find_col(headers, _STOCK_CODE_KEYS) is not None and
                _find_col(headers, _STOCK_QTY_KEYS)  is not None)
    is_fund  = (_find_col(headers, _FUND_CODE_KEYS)  is not None and
                _find_col(headers, _FUND_QTY_KEYS)   is not None)

    if is_stock:
        _parse_stock_rows(headers, rows[1:], positions, errors)
    elif is_fund:
        _parse_fund_rows(headers, rows[1:], positions, errors)


def _parse_stock_rows(headers, rows, positions, errors):
    code_col = _find_col(headers, _STOCK_CODE_KEYS)
    name_col = _find_col(headers, _STOCK_NAME_KEYS)
    qty_col  = _find_col(headers, _STOCK_QTY_KEYS)
    mv_col   = _find_col(headers, _STOCK_MV_KEYS)

    for i, row in enumerate(rows):
        try:
            cells = [_cell(c) for c in row]
            code  = cells[code_col] if code_col < len(cells) else ""
            if not _is_valid_code(code):
                continue

            name   = cells[name_col] if name_col is not None and name_col < len(cells) else ""
            qty    = _to_float(cells[qty_col]  if qty_col < len(cells) else "0")
            mv_wan = _to_float(cells[mv_col]   if mv_col  is not None and mv_col < len(cells) else "0")

            if qty <= 0:
                continue

            market_value  = round(mv_wan * 10000, 2)
            current_price = round(market_value / qty, 4) if qty else 0

            positions.append(_make_position(
                code, name, _detect_market(code), "CNY",
                qty, current_price, market_value,
            ))
        except Exception as e:
            errors.append(f"股票第 {i+1} 行解析错误: {e}")


def _parse_fund_rows(headers, rows, positions, errors):
    code_col = _find_col(headers, _FUND_CODE_KEYS)
    name_col = _find_col(headers, _FUND_NAME_KEYS)
    qty_col  = _find_col(headers, _FUND_QTY_KEYS)
    nav_col  = _find_col(headers, _FUND_NAV_KEYS)

    for i, row in enumerate(rows):
        try:
            cells = [_cell(c) for c in row]
            code  = cells[code_col] if code_col < len(cells) else ""
            if not _is_valid_code(code):
                continue

            name    = cells[name_col] if name_col is not None and name_col < len(cells) else ""
            qty     = _to_float(cells[qty_col]  if qty_col < len(cells) else "0")
            nav_wan = _to_float(cells[nav_col]  if nav_col is not None and nav_col < len(cells) else "0")

            if qty <= 0:
                continue

            market_value  = round(nav_wan * 10000, 2)
            current_price = round(market_value / qty, 6) if qty else 0
            is_cash_equiv = is_cash_equivalent(code, name)

            positions.append(_make_position(
                code, name, "A", "CNY",
                qty, current_price, market_value,
                is_cash_equivalent=is_cash_equiv,
            ))
        except Exception as e:
            errors.append(f"基金第 {i+1} 行解析错误: {e}")


# ── 文本回退解析 ──────────────────────────────────────────────────────────

def _parse_text_fallback(text: str, positions: List, errors: List):
    """
    当 find_tables() 找不到表格时，从纯文本按行重建数据。
    适用于无边框表格的 PDF 导出。
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    in_stock = False
    in_fund  = False
    stock_header_found = False
    fund_header_found  = False

    for line in lines:
        # 检测章节标记
        if "股票持仓" in line:
            in_stock, in_fund = True, False
            stock_header_found = False
            continue
        if "基金持仓" in line:
            in_stock, in_fund = False, True
            fund_header_found = False
            continue

        tokens = line.split()
        if not tokens:
            continue

        if in_stock:
            if not stock_header_found:
                if any("代码" in t for t in tokens):
                    stock_header_found = True
                continue
            # 找到以 5-6 位数字开头或包含的行
            code = next((t for t in tokens if _is_valid_code(t)), None)
            if not code:
                continue
            idx = tokens.index(code)
            try:
                # 名称：code 之后第一个非数字 token
                name = ""
                if idx + 1 < len(tokens) and not re.match(r"^[\d,\.]+$", tokens[idx + 1]):
                    name = tokens[idx + 1]
                # 数字字段：code 之后所有纯数字 token → 第1个=数量，第2个=市值（万元）
                nums = [t for t in tokens[idx + 1:] if re.match(r"^[\d,\.]+$", t)]
                if len(nums) < 2:
                    continue
                qty    = _to_float(nums[0])
                mv_wan = _to_float(nums[1])
                if qty <= 0:
                    continue
                mv = round(mv_wan * 10000, 2)
                positions.append(_make_position(
                    code, name, _detect_market(code), "CNY",
                    qty, round(mv / qty, 4) if qty else 0, mv,
                ))
            except Exception as e:
                errors.append(f"文本回退-股票行解析错误: {line!r} → {e}")

        elif in_fund:
            if not fund_header_found:
                if any("代码" in t or "份额" in t for t in tokens):
                    fund_header_found = True
                continue
            code = next((t for t in tokens if _is_valid_code(t)), None)
            if not code:
                continue
            idx = tokens.index(code)
            try:
                name = ""
                if idx + 1 < len(tokens) and not re.match(r"^[\d,\.]+$", tokens[idx + 1]):
                    name = tokens[idx + 1]
                nums = [t for t in tokens[idx + 1:] if re.match(r"^[\d,\.]+$", t)]
                if len(nums) < 2:
                    continue
                qty     = _to_float(nums[0])
                nav_wan = _to_float(nums[1])
                if qty <= 0:
                    continue
                mv = round(nav_wan * 10000, 2)
                is_cash_equiv = is_cash_equivalent(code, name)
                positions.append(_make_position(
                    code, name, "A", "CNY",
                    qty, round(mv / qty, 6) if qty else 0, mv,
                    is_cash_equivalent=is_cash_equiv,
                ))
            except Exception as e:
                errors.append(f"文本回退-基金行解析错误: {line!r} → {e}")


# ── 工具函数 ──────────────────────────────────────────────────────────────

def _make_position(symbol, name, market, currency, quantity,
                   current_price, market_value, *, is_cash_equivalent=False):
    return {
        "symbol":             symbol,
        "name":               name,
        "market":             market,
        "currency":           currency,
        "quantity":           quantity,
        "cost_price":         0,          # PDF 不含成本价
        "current_price":      current_price,
        "market_value":       market_value,
        "unrealized_pnl":     0,
        "unrealized_pnl_pct": 0,
        "broker":             "csv",
        "is_cash_equivalent": is_cash_equivalent,
    }


def _cell(val) -> str:
    """清理单元格：去首尾空白、合并内部换行"""
    return re.sub(r"\s+", " ", str(val or "")).strip()


def _find_col(headers: List[str], candidates: List[str]) -> int | None:
    """精确匹配优先，再做子串匹配"""
    for c in candidates:
        if c in headers:
            return headers.index(c)
    for i, h in enumerate(headers):
        for c in candidates:
            if c in h:
                return i
    return None


def _is_valid_code(code: str) -> bool:
    return bool(re.match(r"^\d{5,6}$", code))


def _detect_market(code: str) -> str:
    return "HK" if len(code) == 5 else "A"


def _to_float(val: str) -> float:
    val = re.sub(r"[,，\s]", "", str(val))
    try:
        return float(val)
    except ValueError:
        return 0.0
