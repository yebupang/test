"use client";

import { useState } from "react";
import useSWR from "swr";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, Legend,
} from "recharts";
import { getProfitHistory } from "@/lib/api";
import { DailySnapshot } from "@/lib/types";

const RANGE_OPTIONS = [
  { label: "30天", days: 30 },
  { label: "90天", days: 90 },
  { label: "180天", days: 180 },
  { label: "1年", days: 365 },
];

function fmtAmt(n: number) {
  if (Math.abs(n) >= 1_000_000) return `¥${(n / 1_000_000).toFixed(2)}M`;
  if (Math.abs(n) >= 10_000) return `¥${(n / 10_000).toFixed(1)}万`;
  return `¥${n.toFixed(0)}`;
}

function fmtDate(s: string) {
  const d = new Date(s);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

interface Props {
  accountId?: number | null;  // null / undefined = 全账户合计
  accountName?: string;
}

export default function ProfitChart({ accountId, accountName }: Props) {
  const [days, setDays] = useState(90);

  const key = `/portfolio/profit-history?account_id=${accountId ?? ""}&days=${days}`;
  const { data, isLoading } = useSWR<DailySnapshot[]>(
    key,
    () => getProfitHistory(accountId ?? null, days) as Promise<DailySnapshot[]>,
    { refreshInterval: 0 }
  );

  const chartData = (data ?? []).map((s) => ({
    date: fmtDate(s.date),
    profit: s.profit_cny,
    returnPct: s.return_pct ?? 0,
    totalAssets: s.total_assets_cny,
  }));

  const hasData = chartData.length > 0;
  const latestProfit = hasData ? chartData[chartData.length - 1].profit : 0;
  const latestReturn = hasData ? chartData[chartData.length - 1].returnPct : 0;
  const isProfitable = latestProfit >= 0;

  return (
    <div className="bg-card p-4">
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div>
          <p className="text-sm text-gray-400">
            {accountName ?? "全账户"}收益曲线
          </p>
          {hasData && (
            <div className="flex items-center gap-3 mt-1">
              <span className={`text-lg font-semibold font-mono ${isProfitable ? "text-emerald-400" : "text-red-400"}`}>
                {isProfitable ? "+" : ""}{fmtAmt(latestProfit)}
              </span>
              <span className={`text-sm font-mono ${isProfitable ? "text-emerald-400" : "text-red-400"}`}>
                {isProfitable ? "+" : ""}{latestReturn.toFixed(2)}%
              </span>
            </div>
          )}
        </div>
        {/* Range selector */}
        <div className="flex gap-1">
          {RANGE_OPTIONS.map((o) => (
            <button
              key={o.days}
              onClick={() => setDays(o.days)}
              className={`px-2 py-1 text-xs rounded transition-colors ${
                days === o.days
                  ? "bg-indigo-600 text-white"
                  : "bg-gray-800 text-gray-400 hover:bg-gray-700"
              }`}
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="h-48 flex items-center justify-center text-gray-500 text-sm">加载中…</div>
      ) : !hasData ? (
        <div className="h-48 flex flex-col items-center justify-center text-gray-500 text-sm gap-2">
          <p>暂无快照数据</p>
          <p className="text-xs text-gray-600">
            每日 UTC 23:00 自动记录；或在同步页手动触发快照
          </p>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis
              dataKey="date"
              tick={{ fill: "#6b7280", fontSize: 11 }}
              tickLine={false}
              interval="preserveStartEnd"
            />
            {/* Left Y: profit amount */}
            <YAxis
              yAxisId="amt"
              orientation="left"
              tick={{ fill: "#6b7280", fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => fmtAmt(v)}
              width={60}
            />
            {/* Right Y: return % */}
            <YAxis
              yAxisId="pct"
              orientation="right"
              tick={{ fill: "#6b7280", fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `${v.toFixed(1)}%`}
              width={48}
            />
            <Tooltip
              contentStyle={{ background: "#111827", border: "1px solid #374151", borderRadius: 6 }}
              labelStyle={{ color: "#9ca3af", fontSize: 11 }}
              itemStyle={{ fontSize: 12 }}
              formatter={(value: number, name: string) => {
                if (name === "盈亏金额") return [fmtAmt(value), name];
                if (name === "收益率") return [`${value.toFixed(2)}%`, name];
                return [fmtAmt(value), name];
              }}
            />
            <Legend
              wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
              iconType="circle"
              iconSize={8}
            />
            <Line
              yAxisId="amt"
              type="monotone"
              dataKey="profit"
              name="盈亏金额"
              stroke="#6366f1"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
            />
            <Line
              yAxisId="pct"
              type="monotone"
              dataKey="returnPct"
              name="收益率"
              stroke="#f59e0b"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
              strokeDasharray="4 2"
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
