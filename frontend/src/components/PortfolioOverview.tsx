"use client";

import { PortfolioSummary, MARKET_LABELS, POSITION_TYPE_LABELS } from "@/lib/types";
import PnlBadge from "./PnlBadge";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";

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

function fmt(n: number) {
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

  const equityRatio = data.equity_ratio ?? 0;
  const cashRatio = Math.max(0, 100 - equityRatio);
  const hasCash = data.total_cash > 0;

  return (
    <div className="space-y-4">
      {/* 总资产卡片 */}
      <div className="bg-card p-4 md:p-6">
        <p className="text-xs text-gray-400 mb-1">总资产{hasCash ? "（股票 + 现金）" : ""}</p>
        <p className="text-3xl font-bold font-mono">
          ${fmt(hasCash ? data.total_assets : data.total_market_value)}
        </p>
        <div className="flex items-center gap-3 mt-2">
          <PnlBadge value={data.total_pnl} suffix="" />
          <PnlBadge value={data.total_pnl_pct} />
        </div>

        {/* 仓位进度条 */}
        <div className="mt-4">
          <div className="flex justify-between text-xs text-gray-400 mb-1">
            <span>仓位率</span>
            <span className="font-semibold text-white">{equityRatio}%</span>
          </div>
          <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-indigo-500 rounded-full transition-all duration-500"
              style={{ width: `${equityRatio}%` }}
            />
          </div>
          <div className="flex justify-between text-xs mt-1">
            <span className="text-indigo-400">股票 ${fmt(data.total_market_value)}</span>
            {hasCash && (
              <span className="text-gray-400">现金 ${fmt(data.total_cash)}</span>
            )}
          </div>
        </div>
      </div>

      {/* 指标卡片行 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: "股票市值", value: `$${fmt(data.total_market_value)}` },
          { label: "总成本", value: `$${fmt(data.total_cost)}` },
          { label: "浮动盈亏", value: <PnlBadge value={data.total_pnl} suffix="" /> },
          { label: "持仓股数", value: data.accounts.reduce((s, a) => s + a.positions.length, 0) },
        ].map((item, i) => (
          <div key={i} className="bg-card p-3 md:p-4">
            <p className="text-xs text-gray-400 mb-1">{item.label}</p>
            <p className="text-lg font-semibold">{item.value}</p>
          </div>
        ))}
      </div>

      {/* 各账户现金 */}
      {hasCash && (
        <div className="bg-card p-4">
          <p className="text-sm text-gray-400 mb-3">各账户现金余额</p>
          <div className="space-y-2">
            {data.accounts.map((acc) => (
              <div key={acc.account.id} className="flex items-center justify-between text-sm">
                <span className="text-gray-300">{acc.account.name}</span>
                <div className="flex items-center gap-4">
                  <span className="text-gray-400">
                    {acc.cash_currency} {fmt(acc.cash_balance)}
                  </span>
                  <div className="w-24 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-indigo-500 rounded-full"
                      style={{ width: `${acc.equity_ratio}%` }}
                    />
                  </div>
                  <span className="text-xs text-gray-400 w-16 text-right">
                    股{acc.equity_ratio}% / 金{Math.max(0, 100 - acc.equity_ratio).toFixed(1)}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 图表行 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* 市场分布 */}
        <div className="bg-card p-4">
          <p className="text-sm text-gray-400 mb-3">市场分布</p>
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie
                data={marketPie}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={70}
                label={({ name, pct }) => `${name} ${pct}%`}
              >
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
              <Pie
                data={typePie}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={70}
                label={({ name, pct }) => `${name} ${pct}%`}
              >
                {typePie.map((entry) => (
                  <Cell key={entry.key} fill={TYPE_COLORS[entry.key] || "#888"} />
                ))}
              </Pie>
              <Tooltip formatter={(v: number) => `$${fmt(v)}`} />
            </PieChart>
          </ResponsiveContainer>
          {typePie.length === 0 && (
            <p className="text-center text-gray-500 text-sm mt-4">
              尚未分类仓位，在持仓列表中可设置
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
