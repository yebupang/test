"""
华宝证券 APP 持仓截图 OCR 解析器

使用 Claude Vision API 从持仓页面截图中提取持仓数据。
支持格式：华宝证券 APP「持仓」页面截图（PNG/JPG/JPEG/WEBP）

截图格式示例：
  腾讯控股        560.472    900    -52831.08
  00700.HK        493.200    900    -12.00%    9.52%
  387329.69

  通信ETF         1.161     41900   +3253.07
  515880.SH       1.239     41900   +6.69%    1.28%
  51914.10

代码格式：XXXXX.HK → HK市场；XXXXXX.SH / XXXXXX.SZ → A股
市值为人民币元（非万元）。
"""

import base64
import json
import logging
import re
from typing import List, Dict, Any, Tuple

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
这是一张华宝证券 APP「持仓」页面的截图。请提取所有可见持仓的信息。

每个持仓通常显示为：
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
- 只提取持仓明细行，忽略汇总行（账户资产、总市值等顶部信息）
- 市值是绝对金额（人民币元），不是万元
- 如果某字段看不清，填 null

以下面的 JSON 格式返回，只返回 JSON，不要其他文字：
{
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


def parse_huabao_image(
    content: bytes,
    media_type: str = "image/jpeg",
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    解析华宝证券 APP 持仓截图。

    :param content:    图片文件字节内容
    :param media_type: 图片 MIME 类型，如 image/jpeg 或 image/png
    :return:           (持仓列表, 错误信息列表)
    """
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic 未安装，请运行: pip install anthropic")

    positions: List[Dict[str, Any]] = []
    errors: List[str] = []

    try:
        from config import get_settings
        settings = get_settings()
        client_kwargs = {}
        if settings.anthropic_api_key:
            client_kwargs["api_key"] = settings.anthropic_api_key

        client = anthropic.Anthropic(**client_kwargs)
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
        logger.debug(f"Claude OCR 原始响应: {text[:500]}")

        # 提取 JSON（允许 Claude 输出前后有少量文字）
        json_match = re.search(r'\{[\s\S]*\}', text)
        if not json_match:
            errors.append(f"Claude 返回内容无法解析为 JSON: {text[:300]}")
            return positions, errors

        data = json.loads(json_match.group())
        raw_positions = data.get("positions", [])

        for item in raw_positions:
            try:
                code = str(item.get("code") or "").strip()
                if not re.match(r'^\d{5,6}$', code):
                    continue

                name         = str(item.get("name") or "").strip()
                market       = str(item.get("market") or "A").strip().upper()
                market_value = float(item.get("market_value") or 0)
                cost_price   = float(item.get("cost_price") or 0)
                current_price = float(item.get("current_price") or 0)
                quantity     = float(item.get("quantity") or 0)

                if quantity <= 0 or market_value <= 0:
                    continue

                positions.append({
                    "symbol":             code,
                    "name":               name,
                    "market":             market if market == "HK" else "A",
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
                errors.append(f"持仓项解析错误: {e}，原始数据: {item}")

    except Exception as e:
        errors.append(f"图片 OCR 失败: {e}")
        logger.exception("图片 OCR 解析异常")

    if not positions and not errors:
        errors.append("未从截图中解析到持仓数据，请确认截图为华宝证券「持仓」页面")

    logger.info(f"图片 OCR 导入: {len(positions)} 条持仓，{len(errors)} 条错误")
    return positions, errors
