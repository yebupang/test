"""
同花顺客户端 Broker — 通过 easytrader 读取已绑定券商的持仓数据
支持所有已在同花顺中绑定的券商（如华宝证券等）

前提条件：
  1. Windows 环境（easytrader 依赖 pywinauto，仅支持 Windows）
  2. 同花顺客户端已启动并登录（xiadan.exe 正在运行）
  3. 已安装依赖：pip install easytrader

在 .env 中配置：
  THS_CLIENT_PATH=C:\\同花顺软件\\同花顺\\xiadan.exe
"""

import logging
import platform
from typing import Dict, Any

logger = logging.getLogger(__name__)


class THSBroker:
    """同花顺客户端持仓读取（easytrader GUI 自动化封装）"""

    # user.balance 中候选的现金余额字段名（各版本同花顺可能不同）
    _CASH_KEYS = ("资金余额", "可用资金", "可取资金", "冻结资金")

    def __init__(self, client_path: str = r"C:\同花顺软件\同花顺\xiadan.exe"):
        self.client_path = client_path
        self._user = None

    def _connect(self):
        if platform.system() != "Windows":
            raise RuntimeError(
                "easytrader 依赖 pywinauto，仅支持 Windows 系统。\n"
                "非 Windows 环境请使用 CSV 导入方式替代。"
            )
        try:
            import easytrader
        except ImportError:
            raise RuntimeError(
                "easytrader 未安装，请运行：pip install easytrader"
            )
        try:
            self._user = easytrader.use("ths")
            self._user.connect(self.client_path)
            logger.info(f"同花顺客户端连接成功: {self.client_path}")
        except Exception as e:
            raise RuntimeError(
                f"同花顺客户端连接失败: {e}\n"
                f"请确认同花顺已启动，路径正确: {self.client_path}"
            )

    def get_positions(self) -> Dict[str, Any]:
        """
        读取同花顺所有持仓和现金。

        easytrader 返回字段：
          stock_code      → symbol
          stock_name      → name
          current_amount  → quantity（当前持有数量）
          cost_price      → cost_price（摊薄成本价）
          last_price      → current_price（最新价）
          market_value    → market_value（持仓市值）
          income_balance  → unrealized_pnl（浮动盈亏金额）
        """
        self._connect()
        try:
            raw_positions = self._user.position
            balance = self._user.balance
            logger.debug(f"同花顺原始持仓: {raw_positions}")
            logger.debug(f"同花顺原始资金: {balance}")
        except Exception as e:
            raise RuntimeError(f"读取同花顺数据失败: {e}")

        positions = []
        for p in (raw_positions or []):
            symbol = str(p.get("stock_code", "") or "").strip()
            if not symbol:
                continue

            quantity = float(p.get("current_amount", 0) or 0)
            if quantity <= 0:
                continue

            name = str(p.get("stock_name", "") or "").strip()
            cost_price = float(p.get("cost_price", 0) or 0)
            current_price = float(p.get("last_price", 0) or 0)
            market_value = float(p.get("market_value", 0) or 0)
            unrealized_pnl = float(p.get("income_balance", 0) or 0)

            # 兜底：市值为空时自行计算
            if market_value == 0 and current_price > 0:
                market_value = current_price * quantity
            cost_total = cost_price * quantity
            pnl_pct = (unrealized_pnl / cost_total * 100) if cost_total > 0 else 0

            market = self._detect_market(symbol)
            currency = "HKD" if market == "HK" else "CNY"

            positions.append({
                "symbol": symbol,
                "name": name,
                "market": market,
                "currency": currency,
                "quantity": quantity,
                "cost_price": cost_price,
                "current_price": current_price,
                "market_value": market_value,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_pct": pnl_pct,
                "broker": "ths",
                "is_cash_equivalent": False,
            })

        # 提取现金余额（遍历候选 key，取第一个非空值）
        cash_amount = 0.0
        for key in self._CASH_KEYS:
            val = (balance or {}).get(key)
            if val is not None:
                try:
                    cash_amount = float(val)
                    break
                except (ValueError, TypeError):
                    continue

        logger.info(f"同花顺持仓: {len(positions)} 条，现金: {cash_amount:.2f} CNY")
        return {
            "positions": positions,
            "cash": {"amount": cash_amount, "currency": "CNY"},
        }

    def _detect_market(self, symbol: str) -> str:
        """根据股票代码格式判断市场"""
        digits = "".join(c for c in symbol if c.isdigit())
        # 港股：5 位数字（含前导零，如 00700）
        if len(digits) == 5 and symbol.isdigit():
            return "HK"
        # A 股：6 位数字
        if len(digits) == 6:
            return "A"
        return "A"  # 华宝证券以 A 股为主，默认 A
