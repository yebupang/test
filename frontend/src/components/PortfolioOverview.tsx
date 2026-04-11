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

/** 人民币格式化 */
function fmtCny(n: number) {
  if (Math.abs(n) >= 1_000_000) return `¥${(n / 1_000_000).toFixed(2)}M`;
  if (Math.abs(n) >= 10_000) return `¥${(n / 10_000).toFixed(1)}万`;
  return `¥${n.toFixed(0)}`;
}

/** 原币格式化，根据 currency 选择货币符号 */
function fmtRaw(n: number, currency = "USD") {
  const sym = currency === "HKD" ? "HK$" : currency === "CNY" ? "¥" : "$";
  if (Math.abs(n) >= 1_000_000) return `${sym}${(n / 1_000_000).toFixed(2)}M`;
  if (Math.abs(n) >= 1_000) return `${sym}${(n / 1_000).toFixed(1)}K`;
  return `${sym}${n.toFixed(2)}`;
}

interface Props {
  data: PortfolioSummary;
}

export default function PortfolioOverview({ data }: Props) {
  const fx = data.exchange_rates ?? {};
  const usdRate = fx["USD"] ?? 7.24;
  const hkdRate = fx["HKD"] ?? 0.93;

  // 饼图数据均用 CNY 市值，确保图形比例与百分比一致
  const marketPie = Object.entries(data.by_market)
    .filter(([, val]) => (val.market_value_cny ?? val.market_value) > 0)
    .map(([key, val]) => ({
      name: MARKET_LABELS[key as keyof typeof MARKET_LABELS] || key,
      value: val.market_value_cny,
      pct: val.pct,
      key,
    }));

  const typePie = Object.entries(data.by_position_type)
    .filter(([, val]) => (val.market_value_cny ?? val.market_value) > 0)
    .map(([key, val]) => ({
      name: POSITION_TYPE_LABELS[key] || key,
      value: val.market_value_cny,
      pct: val.pct,
      key,
    }));

  const equityRatio = data.equity_ratio ?? 0;
  const hasCash = data.total_cash_cny > 0;

  return (
    <div className="space-y-4">
      {/* 总资产卡片 */}
      <div className="bg-card p-4 md:p-6">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs text-gray-400 mb-1">总资产（人民币）</p>
            <p className="text-3xl font-bold font-mono">
              {fmtCny(data.total_assets_cny)}
            </p>
            <div className="flex items-center gap-3 mt-2">
              <PnlBadge value={data.total_pnl_cny} suffix="" prefix="¥" />
              <PnlBadge value={data.total_pnl_pct} />
            </div>
          </div>
          {/* 实时汇率 */}
          <div className="text-right text-xs text-gray-500 space-y-1">
            <div>1 USD = <span className="text-gray-300">{usdRate.toFixed(4)}</span> CNY</div>
            <div>1 HKD = <span className="text-gray-300">{hkdRate.toFixed(4)}</span> CNY</div>
          </div>
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
            <span className="text-indigo-400">股票 {fmtCny(data.total_market_value_cny)}</span>
            {hasCash && <span className="text-gray-400">现金 {fmtCny(data.total_cash_cny)}</span>}
          </div>
        </div>
      </div>

      {/* 指标卡片行 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: "股票市值（¥）", value: fmtCny(data.total_market_value_cny) },
          { label: "总成本（¥）",   value: fmtCny(data.total_cost_cny) },
          { label: "浮动盈亏（¥）", value: <PnlBadge value={data.total_pnl_cny} suffix="" prefix="¥" /> },
          { label: "持仓股数",       value: data.accounts.reduce((s, a) => s + a.positions.length, 0) },
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
          <p className="text-sm text-gray-400 mb-3">各账户资产明细</p>
          <div className="space-y-2">
            {data.accounts.map((acc) => {
              // cash_cny = 总资产CNY - 股票市值CNY，完全基于CNY计算，无汇率混算
              const cashCny = acc.total_assets_cny - acc.total_market_value_cny;
              return (
                <div key={acc.account.id} className="flex items-center justify-between text-sm">
                  <span className="text-gray-300">{acc.account.name}</span>
                  <div className="flex items-center gap-3">
                    <div className="text-right">
                      <div className="text-gray-300 font-mono text-xs">
                        股票 {fmtCny(acc.total_market_value_cny)}
                        {cashCny > 0 && (
                          <span className="text-gray-500 ml-2">
                            现金 {fmtRaw(acc.cash_balance, acc.cash_currency)}
                            <span className="text-gray-600 ml-1">≈{fmtCny(cashCny)}</span>
                          </span>
                        )}
                      </div>
                      <div className="text-gray-500 text-xs">合计 {fmtCny(acc.total_assets_cny)}</div>
                    </div>
                    <div className="flex items-center gap-1">
                      <div className="w-16 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                        <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${acc.equity_ratio}%` }} />
                      </div>
                      <span className="text-xs text-gray-500 w-10 text-right">{acc.equity_ratio}%仓</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          {/* 汇总行 */}
          <div className="mt-3 pt-3 border-t border-gray-800 flex justify-between text-sm">
            <span className="text-gray-400">合计</span>
            <span className="font-semibold font-mono">{fmtCny(data.total_assets_cny)}</span>
          </div>
        </div>
      )}

      {/* 图表行 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* 市场分布 */}
        <div className="bg-card p-4">
          <p className="text-sm text-gray-400 mb-3">市场分布（人民币）</p>
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
                labelLine={false}
              >
                {marketPie.map((entry) => (
                  <Cell key={entry.key} fill={MARKET_COLORS[entry.key] || "#888"} />
                ))}
              </Pie>
              <Tooltip
                formatter={(v: number) => [fmtCny(v), "市值"]}
                contentStyle={{ background: "#1f2937", border: "none", borderRadius: 6 }}
                itemStyle={{ color: "#d1d5db" }}
              />
            </PieChart>
          </ResponsiveContainer>
          {/* 市场明细：显示 CNY 市值 + 占比 + 盈亏 */}
          <div className="space-y-1.5 mt-3">
            {Object.entries(data.by_market).map(([key, val]) => (
              <div key={key} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-1.5">
                  <span
                    className="inline-block w-2 h-2 rounded-full"
                    style={{ background: MARKET_COLORS[key] || "#888" }}
                  />
                  <span className="text-gray-300">{MARKET_LABELS[key as keyof typeof MARKET_LABELS] || key}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-gray-400 font-mono">{fmtCny(val.market_value_cny)}</span>
                  <span className="text-gray-300 w-10 text-right font-semibold">{val.pct}%</span>
                  <PnlBadge value={val.pnl_cny} suffix="" prefix="¥" className="text-xs w-20 text-right" />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 仓位类型分布 */}
        <div className="bg-card p-4">
          <p className="text-sm text-gray-400 mb-3">仓位类型分布（人民币）</p>
          {typePie.length > 0 ? (
            <>
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
                    labelLine={false}
                  >
                    {typePie.map((entry) => (
                      <Cell key={entry.key} fill={TYPE_COLORS[entry.key] || "#888"} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(v: number) => [fmtCny(v), "市值"]}
                    contentStyle={{ background: "#1f2937", border: "none", borderRadius: 6 }}
                    itemStyle={{ color: "#d1d5db" }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="space-y-1.5 mt-3">
                {typePie.map((entry) => (
                  <div key={entry.key} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-1.5">
                      <span
                        className="inline-block w-2 h-2 rounded-full"
                        style={{ background: TYPE_COLORS[entry.key] || "#888" }}
                      />
                      <span className="text-gray-300">{entry.name}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-gray-400 font-mono">{fmtCny(entry.value)}</span>
                      <span className="text-gray-300 w-10 text-right font-semibold">{entry.pct}%</span>
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="text-center text-gray-500 text-sm mt-16">尚未分类仓位，在持仓列表中可设置</p>
          )}
        </div>
      </div>
    </div>
  );
}
