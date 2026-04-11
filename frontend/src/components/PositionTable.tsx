"use client";

import { useState } from "react";
import { Position, MARKET_LABELS, POSITION_TYPE_LABELS, POSITION_TYPE_COLORS } from "@/lib/types";
import PnlBadge from "./PnlBadge";
import { updatePosition } from "@/lib/api";

interface Props {
  positions: Position[];
  onUpdated: () => void;
}

const POSITION_TYPES = [
  { value: "bottom_fishing", label: "抄底" },
  { value: "defensive", label: "防守" },
  { value: "allocation", label: "配置" },
  { value: "volatile", label: "波动" },
  { value: "speculative", label: "投机" },
];

function currSym(currency?: string) {
  if (currency === "HKD") return "HK$";
  if (currency === "CNY") return "¥";
  return "$"; // USD default
}

function fmt(n?: number, digits = 2) {
  if (n == null) return "—";
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toFixed(digits);
}

function fmtPrice(n?: number, currency?: string) {
  if (n == null) return "—";
  const sym = currSym(currency);
  if (Math.abs(n) >= 1_000_000) return `${sym}${(n / 1_000_000).toFixed(2)}M`;
  if (Math.abs(n) >= 1_000) return `${sym}${(n / 1_000).toFixed(1)}K`;
  return `${sym}${n.toFixed(2)}`;
}

function fmtMv(n?: number, currency?: string) {
  if (n == null) return "—";
  const sym = currSym(currency);
  if (Math.abs(n) >= 1_000_000) return `${sym}${(n / 1_000_000).toFixed(2)}M`;
  if (Math.abs(n) >= 10_000) return `${sym}${(n / 10_000).toFixed(1)}万`;
  if (Math.abs(n) >= 1_000) return `${sym}${(n / 1_000).toFixed(1)}K`;
  return `${sym}${n.toFixed(0)}`;
}

export default function PositionTable({ positions, onUpdated }: Props) {
  const [filterMarket, setFilterMarket] = useState<string>("ALL");
  const [sortBy, setSortBy] = useState<keyof Position>("market_value");
  const [editingId, setEditingId] = useState<number | null>(null);

  const filtered = positions
    .filter((p) => filterMarket === "ALL" || p.market === filterMarket)
    .sort((a, b) => {
      const av = (a[sortBy] as number) ?? 0;
      const bv = (b[sortBy] as number) ?? 0;
      return bv - av;
    });

  const handleTypeChange = async (pos: Position, newType: string) => {
    try {
      await updatePosition(pos.id, { position_type: newType });
      onUpdated();
    } catch (e) {
      alert("更新失败: " + e);
    }
    setEditingId(null);
  };

  return (
    <div>
      {/* 过滤栏 */}
      <div className="flex gap-2 mb-3 flex-wrap">
        {["ALL", "US", "HK", "A"].map((m) => (
          <button
            key={m}
            onClick={() => setFilterMarket(m)}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              filterMarket === m
                ? "bg-indigo-600 text-white"
                : "bg-gray-800 text-gray-400 hover:bg-gray-700"
            }`}
          >
            {m === "ALL" ? "全部" : MARKET_LABELS[m as keyof typeof MARKET_LABELS]}
          </button>
        ))}
        <select
          className="ml-auto bg-gray-800 text-gray-300 text-xs rounded px-2 py-1 border border-gray-700"
          value={sortBy as string}
          onChange={(e) => setSortBy(e.target.value as keyof Position)}
        >
          <option value="market_value">按市值排序</option>
          <option value="unrealized_pnl_pct">按盈亏%排序</option>
          <option value="unrealized_pnl">按盈亏金额排序</option>
          <option value="change_pct">按今日涨跌排序</option>
        </select>
      </div>

      {/* 桌面表格 */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b border-gray-800">
              <th className="pb-2 pr-4">股票</th>
              <th className="pb-2 pr-4">市场</th>
              <th className="pb-2 pr-4 text-right">现价</th>
              <th className="pb-2 pr-4 text-right">今日</th>
              <th className="pb-2 pr-4 text-right">持仓量</th>
              <th className="pb-2 pr-4 text-right">市值</th>
              <th className="pb-2 pr-4 text-right">盈亏%</th>
              <th className="pb-2 pr-4 text-right">PE</th>
              <th className="pb-2 pr-4 text-right">PB</th>
              <th className="pb-2">仓位类型</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((pos) => (
              <tr key={pos.id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                <td className="py-3 pr-4">
                  <div className="font-semibold">{pos.symbol}</div>
                  <div className="text-xs text-gray-500">{pos.name}</div>
                </td>
                <td className="py-3 pr-4">
                  <span className="text-xs text-gray-400">{MARKET_LABELS[pos.market]}</span>
                </td>
                <td className="py-3 pr-4 text-right font-mono">{fmtPrice(pos.current_price, pos.currency)}</td>
                <td className="py-3 pr-4 text-right">
                  <PnlBadge value={pos.change_pct ?? 0} />
                </td>
                <td className="py-3 pr-4 text-right font-mono text-gray-300">{fmt(pos.quantity, 0)}</td>
                <td className="py-3 pr-4 text-right font-mono">{fmtMv(pos.market_value, pos.currency)}</td>
                <td className="py-3 pr-4 text-right">
                  <PnlBadge value={pos.unrealized_pnl_pct} />
                </td>
                <td className="py-3 pr-4 text-right text-gray-400">{fmt(pos.pe_ratio)}</td>
                <td className="py-3 pr-4 text-right text-gray-400">{fmt(pos.pb_ratio)}</td>
                <td className="py-3">
                  {editingId === pos.id ? (
                    <select
                      autoFocus
                      className="bg-gray-700 text-xs rounded px-2 py-1 border border-gray-600"
                      defaultValue={pos.position_type || ""}
                      onChange={(e) => handleTypeChange(pos, e.target.value)}
                      onBlur={() => setEditingId(null)}
                    >
                      <option value="">—</option>
                      {POSITION_TYPES.map((t) => (
                        <option key={t.value} value={t.value}>{t.label}</option>
                      ))}
                    </select>
                  ) : (
                    <button
                      onClick={() => setEditingId(pos.id)}
                      className={`text-xs px-2 py-0.5 rounded-full ${
                        POSITION_TYPE_COLORS[pos.position_type || "unclassified"]
                      }`}
                    >
                      {POSITION_TYPE_LABELS[pos.position_type || "unclassified"]}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <p className="text-center text-gray-500 py-8">暂无持仓数据</p>
        )}
      </div>

      {/* 移动端卡片 */}
      <div className="md:hidden space-y-2">
        {filtered.map((pos) => (
          <div key={pos.id} className="bg-card p-3">
            <div className="flex justify-between items-start mb-2">
              <div>
                <span className="font-semibold">{pos.symbol}</span>
                <span className="text-gray-500 text-xs ml-2">{pos.name}</span>
              </div>
              <button
                onClick={() => setEditingId(editingId === pos.id ? null : pos.id)}
                className={`text-xs px-2 py-0.5 rounded-full ${
                  POSITION_TYPE_COLORS[pos.position_type || "unclassified"]
                }`}
              >
                {POSITION_TYPE_LABELS[pos.position_type || "unclassified"]}
              </button>
            </div>
            {editingId === pos.id && (
              <div className="mb-2 flex gap-1 flex-wrap">
                {POSITION_TYPES.map((t) => (
                  <button
                    key={t.value}
                    onClick={() => handleTypeChange(pos, t.value)}
                    className="text-xs bg-gray-700 hover:bg-gray-600 px-2 py-1 rounded"
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            )}
            <div className="grid grid-cols-3 gap-2 text-sm">
              <div>
                <p className="text-gray-500 text-xs">现价</p>
                <p className="font-mono">{fmtPrice(pos.current_price, pos.currency)}</p>
              </div>
              <div>
                <p className="text-gray-500 text-xs">今日</p>
                <PnlBadge value={pos.change_pct ?? 0} />
              </div>
              <div>
                <p className="text-gray-500 text-xs">市值</p>
                <p className="font-mono">{fmtMv(pos.market_value, pos.currency)}</p>
              </div>
              <div>
                <p className="text-gray-500 text-xs">盈亏%</p>
                <PnlBadge value={pos.unrealized_pnl_pct} />
              </div>
              <div>
                <p className="text-gray-500 text-xs">PE</p>
                <p className="text-gray-300">{fmt(pos.pe_ratio)}</p>
              </div>
              <div>
                <p className="text-gray-500 text-xs">PB</p>
                <p className="text-gray-300">{fmt(pos.pb_ratio)}</p>
              </div>
            </div>
            <div className="mt-2">
              <div className="h-1 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-indigo-500 rounded-full"
                  style={{ width: `${Math.min(Math.abs(pos.unrealized_pnl_pct), 100)}%` }}
                />
              </div>
            </div>
          </div>
        ))}
        {filtered.length === 0 && (
          <p className="text-center text-gray-500 py-8">暂无持仓数据</p>
        )}
      </div>
    </div>
  );
}
