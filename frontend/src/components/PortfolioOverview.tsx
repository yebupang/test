"use client";

import { PortfolioSummary, MARKET_LABELS, POSITION_TYPE_LABELS } from "@/lib/types";
import PnlBadge from "./PnlBadge";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from "recharts";

const MARKET_COLORS: Record<string, string> = {
  US: "#6366f1",
  HK: "#f59e0b",
  A: "#ec4899",
};

const TYPE_COLORS: Record<string, string> = {
  bottom_fishing: "#a855f7",
  defensive: "#3b82f6",
  allocation: "#22c55e",
  volatile: "#eab308",
  speculative: "#ef4444",
  unclassified: "#6b7280",
};

function fmt(n: number, currency = "USD") {
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toFixed(2);
}

interface Props {
  data: PortfolioSummary;
}

export default function PortfolioOverview({ data }: Props) {
  const marketPie = Object.entries(data.by_market).map(([key, val]) => ({
    name: MARKET_LABELS[key as keyof typeof MARKET_LABELS] || key,
    value: val.market_value,
    pct: val.pct,
    key,
  }));

  const typePie = Object.entries(data.by_position_type).map(([key, val]) => ({
    name: POSITION_TYPE_LABELS[key] || key,
    value: val.market_value,
    pct: val.pct,
    key,
  }));

  return (
    <div className="space-y-4">
      {/* 总资产卡片 */}
      <div className="bg-card p-4 md:p-6">
        <p className="text-xs text-gray-400 mb-1">总市值</p>
        <p className="text-3xl font-bold font-mono">
          ${fmt(data.total_market_value)}
        </p>
        <div className="flex items-center gap-3 mt-2">
          <PnlBadge value={data.total_pnl} suffix="" />
          <PnlBadge value={data.total_pnl_pct} />
        </div>
      </div>

      {/* 指标卡片行 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: "总成本", value: `$${fmt(data.total_cost)}` },
          { label: "总盈亏", value: <PnlBadge value={data.total_pnl} suffix="" /> },
          { label: "持仓数量", value: data.accounts.reduce((s, a) => s + a.positions.length, 0) },
          { label: "账户数", value: data.accounts.length },
        ].map((item, i) => (
          <div key={i} className="bg-card p-3 md:p-4">
            <p className="text-xs text-gray-400 mb-1">{item.label}</p>
            <p className="text-lg font-semibold">{item.value}</p>
          </div>
        ))}
      </div>

      {/* 图表行 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* 市场分布 */}
        <div className="bg-card p-4">
          <p className="text-sm text-gray-400 mb-3">市场分布</p>
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie data={marketPie} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={70} label={({ name, pct }) => `${name} ${pct}%`}>
                {marketPie.map((entry) => (
                  <Cell key={entry.key} fill={MARKET_COLORS[entry.key] || "#888"} />
                ))}
              </Pie>
              <Tooltip formatter={(v: number) => `$${fmt(v)}`} />
            </PieChart>
          </ResponsiveContainer>
          <div className="grid grid-cols-3 gap-2 mt-2">
            {Object.entries(data.by_market).map(([key, val]) => (
              <div key={key} className="text-center">
                <div className="text-xs text-gray-400">{MARKET_LABELS[key as keyof typeof MARKET_LABELS] || key}</div>
                <div className="text-sm font-semibold">{val.pct}%</div>
                <PnlBadge value={val.pnl} suffix="" className="text-xs" />
              </div>
            ))}
          </div>
        </div>

        {/* 仓位类型分布 */}
        <div className="bg-card p-4">
          <p className="text-sm text-gray-400 mb-3">仓位类型分布</p>
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie data={typePie} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={70} label={({ name, pct }) => `${name} ${pct}%`}>
                {typePie.map((entry) => (
                  <Cell key={entry.key} fill={TYPE_COLORS[entry.key] || "#888"} />
                ))}
              </Pie>
              <Tooltip formatter={(v: number) => `$${fmt(v)}`} />
            </PieChart>
          </ResponsiveContainer>
          {typePie.length === 0 && (
            <p className="text-center text-gray-500 text-sm mt-4">尚未分类仓位，在持仓列表中可设置</p>
          )}
        </div>
      </div>
    </div>
  );
}
