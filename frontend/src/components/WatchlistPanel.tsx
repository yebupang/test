"use client";

import { useState } from "react";
import useSWR from "swr";
import { WatchListItem, MARKET_LABELS } from "@/lib/types";
import { getWatchlist, addToWatchlist, removeFromWatchlist, updateWatchlistItem } from "@/lib/api";
import PnlBadge from "./PnlBadge";
import { Plus, Trash2, Edit2, Check, X } from "lucide-react";

function fmt(n?: number) {
  if (n == null) return "—";
  return n.toFixed(2);
}

function TargetBadge({ current, target }: { current?: number; target?: number }) {
  if (!current || !target) return null;
  const diff = ((target - current) / current) * 100;
  return <span className={`text-xs ml-1 ${diff > 0 ? "text-gray-400" : "text-red-400"}`}>目标{diff > 0 ? "+" : ""}{diff.toFixed(1)}%</span>;
}

export default function WatchlistPanel() {
  const { data: items = [], mutate } = useSWR<WatchListItem[]>("/watchlist/", getWatchlist);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ symbol: "", market: "US", note: "", target_price: "" });
  const [editId, setEditId] = useState<number | null>(null);
  const [editNote, setEditNote] = useState("");

  const handleAdd = async () => {
    if (!form.symbol) return;
    try {
      await addToWatchlist({
        symbol: form.symbol.toUpperCase(),
        market: form.market,
        note: form.note,
        target_price: form.target_price ? parseFloat(form.target_price) : undefined,
      });
      await mutate();
      setForm({ symbol: "", market: "US", note: "", target_price: "" });
      setAdding(false);
    } catch (e: unknown) {
      alert((e as Error).message);
    }
  };

  const handleRemove = async (id: number) => {
    if (!confirm("确认移除？")) return;
    await removeFromWatchlist(id);
    await mutate();
  };

  const handleSaveNote = async (id: number) => {
    await updateWatchlistItem(id, { note: editNote });
    await mutate();
    setEditId(null);
  };

  return (
    <div className="space-y-3">
      {/* 添加按钮 */}
      <div className="flex justify-between items-center">
        <p className="text-sm text-gray-400">共 {items.length} 只</p>
        <button
          onClick={() => setAdding(!adding)}
          className="flex items-center gap-1 text-xs bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1.5 rounded-lg"
        >
          <Plus size={14} /> 添加关注
        </button>
      </div>

      {/* 添加表单 */}
      {adding && (
        <div className="bg-card p-3 space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <input
              placeholder="股票代码"
              value={form.symbol}
              onChange={(e) => setForm({ ...form, symbol: e.target.value })}
              className="bg-gray-800 rounded px-2 py-1.5 text-sm border border-gray-700 focus:border-indigo-500 outline-none"
            />
            <select
              value={form.market}
              onChange={(e) => setForm({ ...form, market: e.target.value })}
              className="bg-gray-800 rounded px-2 py-1.5 text-sm border border-gray-700"
            >
              <option value="US">美股</option>
              <option value="HK">港股</option>
              <option value="A">A股</option>
            </select>
          </div>
          <input
            placeholder="目标价（可选）"
            type="number"
            value={form.target_price}
            onChange={(e) => setForm({ ...form, target_price: e.target.value })}
            className="w-full bg-gray-800 rounded px-2 py-1.5 text-sm border border-gray-700 focus:border-indigo-500 outline-none"
          />
          <input
            placeholder="备注（可选）"
            value={form.note}
            onChange={(e) => setForm({ ...form, note: e.target.value })}
            className="w-full bg-gray-800 rounded px-2 py-1.5 text-sm border border-gray-700 focus:border-indigo-500 outline-none"
          />
          <div className="flex gap-2">
            <button onClick={handleAdd} className="flex-1 bg-indigo-600 hover:bg-indigo-500 text-white rounded py-1.5 text-sm">确认添加</button>
            <button onClick={() => setAdding(false)} className="flex-1 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded py-1.5 text-sm">取消</button>
          </div>
        </div>
      )}

      {/* 关注列表 */}
      <div className="space-y-2">
        {items.map((item) => (
          <div key={item.id} className="bg-card p-3">
            <div className="flex justify-between items-start">
              <div>
                <span className="font-semibold">{item.symbol}</span>
                <span className="text-xs text-gray-500 ml-2">{MARKET_LABELS[item.market]}</span>
                {item.name && <span className="text-xs text-gray-400 ml-1">{item.name}</span>}
              </div>
              <div className="flex gap-1">
                <button onClick={() => { setEditId(item.id); setEditNote(item.note || ""); }} className="text-gray-500 hover:text-gray-300 p-1">
                  <Edit2 size={14} />
                </button>
                <button onClick={() => handleRemove(item.id)} className="text-gray-500 hover:text-red-400 p-1">
                  <Trash2 size={14} />
                </button>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2 mt-2 text-sm">
              <div>
                <p className="text-xs text-gray-500">现价</p>
                <p className="font-mono">{fmt(item.current_price)}
                  <TargetBadge current={item.current_price} target={item.target_price} />
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500">今日</p>
                <PnlBadge value={item.change_pct ?? 0} />
              </div>
              <div>
                <p className="text-xs text-gray-500">PE</p>
                <p className="text-gray-300">{fmt(item.pe_ratio)}</p>
              </div>
            </div>

            {/* 52周区间 */}
            {item.week_52_high && item.week_52_low && item.current_price && (
              <div className="mt-2">
                <div className="flex justify-between text-xs text-gray-600 mb-0.5">
                  <span>{fmt(item.week_52_low)}</span>
                  <span className="text-gray-500">52周区间</span>
                  <span>{fmt(item.week_52_high)}</span>
                </div>
                <div className="h-1 bg-gray-800 rounded-full">
                  <div
                    className="h-full bg-indigo-500 rounded-full"
                    style={{
                      width: `${Math.min(
                        ((item.current_price - item.week_52_low) /
                          (item.week_52_high - item.week_52_low)) * 100,
                        100
                      )}%`,
                    }}
                  />
                </div>
              </div>
            )}

            {/* 备注编辑 */}
            {editId === item.id ? (
              <div className="mt-2 flex gap-2">
                <input
                  value={editNote}
                  onChange={(e) => setEditNote(e.target.value)}
                  className="flex-1 bg-gray-800 rounded px-2 py-1 text-xs border border-gray-700 outline-none"
                  placeholder="添加备注..."
                />
                <button onClick={() => handleSaveNote(item.id)} className="text-green-400 p-1"><Check size={14} /></button>
                <button onClick={() => setEditId(null)} className="text-gray-400 p-1"><X size={14} /></button>
              </div>
            ) : item.note ? (
              <p className="mt-1.5 text-xs text-gray-500 italic">{item.note}</p>
            ) : null}
          </div>
        ))}
        {items.length === 0 && (
          <p className="text-center text-gray-500 text-sm py-6">暂无关注股票，点击「添加关注」开始</p>
        )}
      </div>
    </div>
  );
}
