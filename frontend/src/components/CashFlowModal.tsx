"use client";

import { useState, useEffect } from "react";
import { X, Trash2, PlusCircle } from "lucide-react";
import { CashFlow } from "@/lib/types";
import { getCashFlows, addCashFlow, deleteCashFlow } from "@/lib/api";

const CURRENCIES = ["CNY", "HKD", "USD"];

interface Props {
  accountId: number;
  accountName: string;
  onClose: () => void;
}

function fmtDate(s: string) {
  return s.slice(0, 10);
}

function fmtAmt(n: number, currency: string) {
  const sym = currency === "HKD" ? "HK$" : currency === "CNY" ? "¥" : "$";
  if (Math.abs(n) >= 1_000_000) return `${sym}${(n / 1_000_000).toFixed(2)}M`;
  if (Math.abs(n) >= 10_000) return `${sym}${(n / 10_000).toFixed(1)}万`;
  if (Math.abs(n) >= 1_000) return `${sym}${(n / 1_000).toFixed(1)}K`;
  return `${sym}${n.toLocaleString()}`;
}

export default function CashFlowModal({ accountId, accountName, onClose }: Props) {
  const [flows, setFlows] = useState<CashFlow[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  // form state
  const today = new Date().toISOString().slice(0, 10);
  const [kind, setKind] = useState<"deposit" | "withdraw">("deposit");
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("CNY");
  const [flowDate, setFlowDate] = useState(today);
  const [note, setNote] = useState("");

  const load = async () => {
    try {
      const data = await getCashFlows(accountId) as CashFlow[];
      setFlows(data);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [accountId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const n = parseFloat(amount);
    if (!n || n <= 0) { setError("请输入正确的金额"); return; }
    setSubmitting(true);
    setError("");
    try {
      await addCashFlow(accountId, { date: flowDate, kind, amount: n, currency, note: note || undefined });
      setAmount("");
      setNote("");
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "提交失败");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (cfId: number) => {
    if (!confirm("确认删除此记录？")) return;
    try {
      await deleteCashFlow(accountId, cfId);
      await load();
    } catch {
      // silent
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
      <div className="bg-gray-900 rounded-xl w-full max-w-md max-h-[90vh] flex flex-col shadow-2xl border border-gray-700">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <div>
            <h2 className="text-sm font-semibold text-white">资金转入/转出</h2>
            <p className="text-xs text-gray-500 mt-0.5">{accountName}</p>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300">
            <X size={18} />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="px-5 py-4 border-b border-gray-800 space-y-3">
          {/* kind toggle */}
          <div className="flex rounded-lg overflow-hidden border border-gray-700">
            {(["deposit", "withdraw"] as const).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setKind(k)}
                className={`flex-1 py-2 text-sm font-medium transition-colors ${
                  kind === k
                    ? k === "deposit"
                      ? "bg-emerald-600 text-white"
                      : "bg-red-600 text-white"
                    : "bg-gray-800 text-gray-400 hover:bg-gray-700"
                }`}
              >
                {k === "deposit" ? "转入" : "转出"}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-3">
            {/* amount */}
            <div>
              <label className="text-xs text-gray-400 block mb-1">金额</label>
              <input
                type="number"
                min="0"
                step="0.01"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="0.00"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-indigo-500"
                required
              />
            </div>
            {/* currency */}
            <div>
              <label className="text-xs text-gray-400 block mb-1">币种</label>
              <select
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
              >
                {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          </div>

          {/* date */}
          <div>
            <label className="text-xs text-gray-400 block mb-1">日期</label>
            <input
              type="date"
              value={flowDate}
              onChange={(e) => setFlowDate(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
              required
            />
          </div>

          {/* note */}
          <div>
            <label className="text-xs text-gray-400 block mb-1">备注（可选）</label>
            <input
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="如：初始建仓资金"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-indigo-500"
            />
          </div>

          {error && <p className="text-xs text-red-400">{error}</p>}

          <button
            type="submit"
            disabled={submitting}
            className="w-full flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-medium py-2.5 rounded-lg transition-colors"
          >
            <PlusCircle size={16} />
            {submitting ? "提交中…" : "确认记录"}
          </button>
        </form>

        {/* History */}
        <div className="flex-1 overflow-y-auto px-5 py-3">
          <p className="text-xs text-gray-500 mb-2">历史记录</p>
          {loading ? (
            <p className="text-xs text-gray-600 text-center py-4">加载中…</p>
          ) : flows.length === 0 ? (
            <p className="text-xs text-gray-600 text-center py-4">暂无记录</p>
          ) : (
            <div className="space-y-2">
              {flows.map((cf) => (
                <div key={cf.id} className="flex items-center justify-between py-1.5 border-b border-gray-800/60">
                  <div>
                    <span className={`text-xs font-medium mr-2 ${cf.kind === "deposit" ? "text-emerald-400" : "text-red-400"}`}>
                      {cf.kind === "deposit" ? "转入" : "转出"}
                    </span>
                    <span className="text-sm font-mono text-white">{fmtAmt(cf.amount, cf.currency)}</span>
                    <span className="text-xs text-gray-500 ml-1">≈¥{cf.amount_cny.toLocaleString()}</span>
                    {cf.note && <p className="text-xs text-gray-500 mt-0.5">{cf.note}</p>}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-500">{fmtDate(cf.date)}</span>
                    <button
                      onClick={() => handleDelete(cf.id)}
                      className="text-gray-600 hover:text-red-400 transition-colors"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
