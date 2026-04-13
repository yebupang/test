"""
华宝证券「上个交易日持仓申报单」PDF 解析器

PDF 实际结构：find_tables() 返回 1 个大表，股票和基金两段合并：
  行0:  ['股票持仓：', None, ...]                 ← 股票段标题
  行1:  ['持有人姓名','股票代码','股票名称',        ← 股票列头
         '前一交易日持股\\n数量','前一交易日市值（万\\n元）','前一交易日融资...']
  行2-N: 股票数据行
  行N+1:['前一交易日持有所有股票的总市值',...]       ← 汇总行（跳过）
  行N+2:['基金持仓：', None, ...]                 ← 基金段标题
  行N+3:['持有人姓名','基金代码','基金简称',        ← 基金列头
         '前一交易日基金份额', None,'前一交易日净值（万元）']
  行N+4-M: 基金数据行

市值/净值单位均为人民币万元；PDF 不含成本价（导入后记为 0）。
依赖：pip install pymupdf
"""

import re
import io
import logging
from typing import List, Dict, Any, Tuple

from brokers.cash_equivalents import is_cash_equivalent

logger = logging.getLogger(__name__)


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
                tab_finder = page.find_tables()
                if tab_finder.tables:
                    # 将所有表格的行合并为一个列表统一处理
                    all_rows: List[List] = []
                    for tab in tab_finder.tables:
                        all_rows.extend(tab.extract())
                    _parse_combined_rows(all_rows, positions, errors)
                else:
                    logger.debug(f"第{page_num}页未找到表格线，回退到文本解析")
                    _parse_text_fallback(page.get_text(), positions, errors)
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


# ── 核心：遍历合并后的行，按段落切换解析模式 ─────────────────────────────

def _parse_combined_rows(rows: List[List], positions: List, errors: List):
    """
    按顺序扫描行，遇到段标题或列头时切换模式，遇到数据行时解析。
    mode: None | "stock" | "fund"
    col_map: {"code": int, "name": int, "qty": int, "value": int}
    """
    mode = None
    col_map: Dict[str, int] = {}

    for row_idx, raw_row in enumerate(rows):
        cells = [_cell(c) for c in raw_row]
        if not any(cells):
            continue
        first = cells[0]

        # ── 段标题行 ──────────────────────────────────────────────────
        if "股票持仓" in first and all(not c for c in cells[1:]):
            mode = "awaiting_stock_header"
            col_map = {}
            continue
        if "基金持仓" in first and all(not c for c in cells[1:]):
            mode = "awaiting_fund_header"
            col_map = {}
            continue

        # ── 汇总行（跳过）────────────────────────────────────────────
        if "总市值" in first or "总净值" in first or "持有所有" in first:
            continue

        # ── 列头行 ────────────────────────────────────────────────────
        if mode == "awaiting_stock_header":
            cm = _detect_stock_cols(cells)
            if cm:
                col_map = cm
                mode = "stock"
            continue

        if mode == "awaiting_fund_header":
            cm = _detect_fund_cols(cells)
            if cm:
                col_map = cm
                mode = "fund"
            continue

        # ── 数据行 ────────────────────────────────────────────────────
        if mode == "stock" and col_map:
            _parse_stock_row(cells, col_map, positions, errors, row_idx)
        elif mode == "fund" and col_map:
            _parse_fund_row(cells, col_map, positions, errors, row_idx)


def _detect_stock_cols(cells: List[str]) -> Dict[str, int]:
    """从列头行提取股票段列索引"""
    cm: Dict[str, int] = {}
    for i, c in enumerate(cells):
        cn = _norm(c)
        if not cm.get("code")  and "股票代码" in cn: cm["code"]  = i
        if not cm.get("name")  and "股票名称" in cn: cm["name"]  = i
        if not cm.get("qty")   and "持股" in cn:      cm["qty"]   = i
        if not cm.get("value") and "市值" in cn:       cm["value"] = i
    return cm if "code" in cm and "qty" in cm and "value" in cm else {}


def _detect_fund_cols(cells: List[str]) -> Dict[str, int]:
    """从列头行提取基金段列索引"""
    cm: Dict[str, int] = {}
    for i, c in enumerate(cells):
        cn = _norm(c)
        if not cm.get("code")  and "基金代码" in cn: cm["code"]  = i
        if not cm.get("name")  and "基金简称" in cn: cm["name"]  = i
        if not cm.get("qty")   and ("基金份额" in cn or ("份额" in cn and "净值" not in cn)): cm["qty"] = i
        if not cm.get("value") and "净值" in cn:     cm["value"] = i
    return cm if "code" in cm and "qty" in cm and "value" in cm else {}


def _parse_stock_row(cells, col_map, positions, errors, row_idx):
    try:
        code = _get(cells, col_map, "code")
        if not _is_valid_code(code):
            return
        name      = _get(cells, col_map, "name")
        qty       = _to_float(_get(cells, col_map, "qty"))
        mv_wan    = _to_float(_get(cells, col_map, "value"))
        if qty <= 0:
            return
        mv            = round(mv_wan * 10000, 2)
        current_price = round(mv / qty, 4) if qty else 0
        positions.append(_make_pos(code, name, _detect_market(code), "CNY",
                                   qty, current_price, mv))
    except Exception as e:
        errors.append(f"股票行{row_idx}解析错误: {e}")


def _parse_fund_row(cells, col_map, positions, errors, row_idx):
    try:
        code = _get(cells, col_map, "code")
        if not _is_valid_code(code):
            return
        name      = _get(cells, col_map, "name")
        qty       = _to_float(_get(cells, col_map, "qty"))
        nav_wan   = _to_float(_get(cells, col_map, "value"))
        if qty <= 0:
            return
        mv            = round(nav_wan * 10000, 2)
        current_price = round(mv / qty, 6) if qty else 0
        positions.append(_make_pos(code, name, "A", "CNY",
                                   qty, current_price, mv,
                                   is_cash_equiv=is_cash_equivalent(code, name)))
    except Exception as e:
        errors.append(f"基金行{row_idx}解析错误: {e}")


# ── 文本回退（无表格线时使用）────────────────────────────────────────────

def _parse_text_fallback(text: str, positions: List, errors: List):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    mode = None
    header_found = False

    for line in lines:
        if "股票持仓" in line:
            mode, header_found = "stock", False
            continue
        if "基金持仓" in line:
            mode, header_found = "fund", False
            continue
        if "总市值" in line or "总净值" in line or "持有所有" in line:
            continue

        tokens = line.split()
        if not tokens:
            continue

        if mode == "stock":
            if not header_found:
                if any("代码" in t for t in tokens):
                    header_found = True
                continue
            code = next((t for t in tokens if _is_valid_code(t)), None)
            if not code:
                continue
            idx = tokens.index(code)
            name = tokens[idx + 1] if idx + 1 < len(tokens) and not re.match(r"^[\d,\.]+$", tokens[idx + 1]) else ""
            nums = [t for t in tokens[idx + 1:] if re.match(r"^[\d,\.]+$", t)]
            if len(nums) < 2:
                continue
            qty, mv_wan = _to_float(nums[0]), _to_float(nums[1])
            if qty <= 0:
                continue
            mv = round(mv_wan * 10000, 2)
            positions.append(_make_pos(code, name, _detect_market(code), "CNY",
                                       qty, round(mv / qty, 4) if qty else 0, mv))

        elif mode == "fund":
            if not header_found:
                if any("代码" in t or "份额" in t for t in tokens):
                    header_found = True
                continue
            code = next((t for t in tokens if _is_valid_code(t)), None)
            if not code:
                continue
            idx = tokens.index(code)
            name = tokens[idx + 1] if idx + 1 < len(tokens) and not re.match(r"^[\d,\.]+$", tokens[idx + 1]) else ""
            nums = [t for t in tokens[idx + 1:] if re.match(r"^[\d,\.]+$", t)]
            if len(nums) < 2:
                continue
            qty, nav_wan = _to_float(nums[0]), _to_float(nums[1])
            if qty <= 0:
                continue
            mv = round(nav_wan * 10000, 2)
            positions.append(_make_pos(code, name, "A", "CNY",
                                       qty, round(mv / qty, 6) if qty else 0, mv,
                                       is_cash_equiv=is_cash_equivalent(code, name)))


# ── 工具函数 ──────────────────────────────────────────────────────────────

def _make_pos(symbol, name, market, currency, quantity, current_price, market_value,
              *, is_cash_equiv=False):
    return {
        "symbol":             symbol,
        "name":               name,
        "market":             market,
        "currency":           currency,
        "quantity":           quantity,
        "cost_price":         0,
        "current_price":      current_price,
        "market_value":       market_value,
        "unrealized_pnl":     0,
        "unrealized_pnl_pct": 0,
        "broker":             "csv",
        "is_cash_equivalent": is_cash_equiv,
    }


def _cell(val) -> str:
    return re.sub(r"\s+", " ", str(val or "")).strip()


def _norm(s: str) -> str:
    """去除所有空白，用于列名模糊匹配"""
    return re.sub(r"\s+", "", s)


def _get(cells: List[str], col_map: Dict[str, int], key: str) -> str:
    idx = col_map.get(key)
    return cells[idx] if idx is not None and idx < len(cells) else ""


def _is_valid_code(code: str) -> bool:
    return bool(re.match(r"^\d{5,6}$", code))


def _detect_market(code: str) -> str:
    return "HK" if len(code) == 5 else "A"


def _to_float(val: str) -> float:
    val = re.sub(r"[,，\s万元]", "", str(val))
    try:
        return float(val)
    except ValueError:
        return 0.0
