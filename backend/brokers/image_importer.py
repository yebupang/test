"""
华宝证券 APP 持仓截图 OCR 解析器

使用 Claude Vision API 从持仓页面截图中提取持仓数据。
支持格式：华宝证券 APP「持仓」页面截图（PNG/JPG/JPEG/WEBP）
支持多张截图同时上传，自动去重（同一证券代码只保留一条）。

截图格式示例：
  腾讯控股        560.472    900    -52831.08
  00700.HK        493.200    900    -12.00%    9.52%
  387329.69

代码格式：XXXXX.HK → HK市场；XXXXXX.SH / XXXXXX.SZ → A股
市值为人民币元（非万元）。
"""

import base64
import json
import logging
import re
from typing import List, Dict, Any, Tuple, Optional

from brokers.cash_equivalents import is_cash_equivalent

logger = logging.getLogger(__name__)

# 支持的图片 MIME 类型
_MEDIA_TYPES = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".webp": "image/webp",
    ".gif":  "image/gif",
}

_PROMPT = """\
这是一张华宝证券 APP「持仓」页面的截图。请提取账户汇总信息和所有可见持仓的信息。

【账户汇总】页面顶部通常显示：
- 账户资产（总资产，人民币元）
- 证券市值（股票+基金市值，人民币元）
- 理财资产（货币基金/理财产品市值，人民币元）
如果页面顶部被遮挡或不可见，对应字段填 null。

【持仓明细】每个持仓通常显示为：
- 第1行：证券名称
- 第2行：代码.市场（如 00700.HK、515880.SH、159201.SZ）及成本价、持仓数量、盈亏
- 第3行：市值（人民币元）及现价

对于每个持仓，提取以下字段：
- code: 纯数字证券代码（如 "00700"、"515880"）
- market: "HK" 表示港股，"A" 表示A股（SH或SZ均为A股）
- name: 证券中文名称
- market_value: 市值（人民币元，数字）
- cost_price: 成本价（数字，可能为0或null）
- current_price: 现价（数字）
- quantity: 持仓数量（数字）

注意：
- 持仓明细只提取个股/基金条目，不要把汇总行当成持仓
- 市值是绝对金额（人民币元），不是万元
- 如果某字段看不清，填 null

以下面的 JSON 格式返回，只返回 JSON，不要其他文字：
{
  "summary": {
    "account_assets": 520000.00,
    "securities_value": 480000.00,
    "wealth_management": 20000.00
  },
  "positions": [
    {
      "code": "00700",
      "market": "HK",
      "name": "腾讯控股",
      "market_value": 387329.69,
      "cost_price": 560.472,
      "current_price": 493.200,
      "quantity": 900
    }
  ]
}
"""


def media_type_from_filename(filename: str) -> str:
    """根据文件名推断图片 MIME 类型"""
    ext = ("." + filename.rsplit(".", 1)[-1]).lower() if "." in filename else ""
    return _MEDIA_TYPES.get(ext, "image/jpeg")


def _ocr_one_image(
    client, content: bytes, media_type: str
) -> Tuple[List[Dict], Optional[Dict[str, float]], List[str]]:
    """调用 Claude 对单张图片做 OCR，返回 (持仓列表, 账户汇总, 错误列表)。

    账户汇总格式: {"account_assets": float, "securities_value": float, "wealth_management": float}
    若页面未显示汇总信息则返回 None。
    """
    positions: List[Dict] = []
    summary: Optional[Dict[str, float]] = None
    errors: List[str] = []

    try:
        image_b64 = base64.standard_b64encode(content).decode("utf-8")
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": _PROMPT},
                ],
            }],
        )

        text = next((b.text for b in response.content if b.type == "text"), "")
        logger.debug(f"Claude OCR 响应(前500字): {text[:500]}")

        json_match = re.search(r'\{[\s\S]*\}', text)
        if not json_match:
            errors.append(f"Claude 返回内容无法解析为 JSON: {text[:200]}")
            return positions, summary, errors

        data = json.loads(json_match.group())

        # ── 账户汇总 ──────────────────────────────────────────────────
        raw_summary = data.get("summary") or {}
        account_assets      = raw_summary.get("account_assets")
        securities_value    = raw_summary.get("securities_value")
        wealth_management   = raw_summary.get("wealth_management")
        if account_assets is not None:
            try:
                summary = {
                    "account_assets":    float(account_assets),
                    "securities_value":  float(securities_value or 0),
                    "wealth_management": float(wealth_management or 0),
                }
            except Exception as e:
                errors.append(f"账户汇总解析错误: {e}")

        # ── 持仓明细 ──────────────────────────────────────────────────
        for item in data.get("positions", []):
            try:
                code = str(item.get("code") or "").strip()
                if not re.match(r'^\d{5,6}$', code):
                    continue
                name          = str(item.get("name") or "").strip()
                market        = str(item.get("market") or "A").strip().upper()
                market_value  = float(item.get("market_value") or 0)
                cost_price    = float(item.get("cost_price") or 0)
                current_price = float(item.get("current_price") or 0)
                quantity      = float(item.get("quantity") or 0)
                if quantity <= 0 or market_value <= 0:
                    continue
                positions.append({
                    "symbol":             code,
                    "name":               name,
                    "market":             "HK" if market == "HK" else "A",
                    "currency":           "CNY",
                    "quantity":           quantity,
                    "cost_price":         cost_price,
                    "current_price":      current_price,
                    "market_value":       round(market_value, 2),
                    "unrealized_pnl":     0,
                    "unrealized_pnl_pct": 0,
                    "broker":             "csv",
                    "is_cash_equivalent": is_cash_equivalent(code, name),
                })
            except Exception as e:
                errors.append(f"持仓项解析错误: {e}，原始: {item}")
    except Exception as e:
        errors.append(f"图片 OCR 失败: {e}")
        logger.exception("图片 OCR 解析异常")

    return positions, summary, errors


def _merge_positions(all_positions: List[Dict]) -> List[Dict]:
    """
    跨图片去重：同一 symbol 只保留一条。
    优先保留 cost_price 不为 0 的条目；若均为 0 则保留 market_value 较大的。
    """
    best: Dict[str, Dict] = {}
    for pos in all_positions:
        sym = pos["symbol"]
        if sym not in best:
            best[sym] = pos
        else:
            prev = best[sym]
            # 优先保留 cost_price 非零的
            if prev["cost_price"] == 0 and pos["cost_price"] != 0:
                best[sym] = pos
            # 同为零或同为非零时，保留 market_value 较大的（数据更完整）
            elif prev["cost_price"] == pos["cost_price"] == 0:
                if pos["market_value"] > prev["market_value"]:
                    best[sym] = pos
    return list(best.values())


def _merge_summary(
    summaries: List[Dict[str, float]],
) -> Optional[Dict[str, float]]:
    """
    合并多张截图的账户汇总：取 account_assets 最大的一条（截图最完整的）。
    计算 A股现金 = 账户资产 - 证券市值 - 理财资产。
    """
    if not summaries:
        return None
    best = max(summaries, key=lambda s: s["account_assets"])
    cash = best["account_assets"] - best["securities_value"] - best["wealth_management"]
    return {
        "account_assets":    best["account_assets"],
        "securities_value":  best["securities_value"],
        "wealth_management": best["wealth_management"],
        "cash":              round(cash, 2),
    }


def parse_huabao_images(
    images: List[Tuple[bytes, str]],
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, float]], List[str]]:
    """
    解析一组华宝证券 APP 持仓截图，自动合并并去重。

    :param images: [(图片字节, media_type), ...]
    :return:       (去重后的持仓列表, 账户汇总含cash字段或None, 所有错误列表)

    账户汇总示例:
    {"account_assets": 520000, "securities_value": 480000,
     "wealth_management": 20000, "cash": 20000}
    """
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic 未安装，请运行: pip install anthropic")

    from config import get_settings
    settings = get_settings()
    client_kwargs = {}
    if settings.anthropic_api_key:
        client_kwargs["api_key"] = settings.anthropic_api_key
    client = anthropic.Anthropic(**client_kwargs)

    all_positions: List[Dict] = []
    all_summaries: List[Dict[str, float]] = []
    all_errors: List[str] = []

    for idx, (content, media_type) in enumerate(images, start=1):
        logger.info(f"正在 OCR 第 {idx}/{len(images)} 张截图 ({media_type})")
        positions, summary, errors = _ocr_one_image(client, content, media_type)
        all_positions.extend(positions)
        if summary:
            all_summaries.append(summary)
        all_errors.extend([f"图片{idx}: {e}" for e in errors])

    merged = _merge_positions(all_positions)
    account_summary = _merge_summary(all_summaries)

    if not merged and not all_errors:
        all_errors.append("未从截图中解析到持仓数据，请确认截图为华宝证券「持仓」页面")

    cash_msg = f"，现金 {account_summary['cash']:.2f} 元" if account_summary else ""
    logger.info(
        f"截图批量导入: {len(images)} 张图片，"
        f"原始 {len(all_positions)} 条 → 去重后 {len(merged)} 条，"
        f"{len(all_errors)} 条错误{cash_msg}"
    )
    return merged, account_summary, all_errors


# ── 单图片入口（向后兼容）────────────────────────────────────────────────
def parse_huabao_image(
    content: bytes,
    media_type: str = "image/jpeg",
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, float]], List[str]]:
    return parse_huabao_images([(content, media_type)])
