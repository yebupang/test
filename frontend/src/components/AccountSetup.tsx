"use client";

import { useState } from "react";
import { createAccount } from "@/lib/api";
import { Account } from "@/lib/types";

const PRESETS = [
  { name: "富途账户（港股+美股）", broker: "futu", market: "HK", currency: "HKD" },
  { name: "盈透账户（美股）", broker: "ib", market: "US", currency: "USD" },
  { name: "华宝账户（A股）", broker: "csv", market: "A", currency: "CNY" },
  { name: "模拟账户（测试）", broker: "mock", market: "US", currency: "USD" },
];

interface Props {
  accounts: Account[];
  onCreated: () => void;
}

export default function AccountSetup({ accounts, onCreated }: Props) {
  const [loading, setLoading] = useState(false);

  const handleCreate = async (preset: typeof PRESETS[0]) => {
    setLoading(true);
    try {
      await createAccount(preset);
      onCreated();
    } catch (e: unknown) {
      alert((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const existingBrokers = accounts.map((a) => a.broker);

  return (
    <div className="bg-card p-6 max-w-lg mx-auto mt-10">
      <h2 className="text-lg font-semibold mb-2">初始化账户</h2>
      <p className="text-sm text-gray-400 mb-5">选择你的券商账户，稍后可在设置中管理</p>
      <div className="space-y-2">
        {PRESETS.map((preset) => {
          const exists = existingBrokers.includes(preset.broker);
          return (
            <button
              key={preset.broker}
              onClick={() => handleCreate(preset)}
              disabled={exists || loading}
              className={`w-full flex items-center justify-between px-4 py-3 rounded-lg border transition-colors ${
                exists
                  ? "border-green-800 bg-green-900/20 text-green-400 cursor-default"
                  : "border-gray-700 hover:border-indigo-500 hover:bg-indigo-900/10"
              }`}
            >
              <span className="text-sm">{preset.name}</span>
              {exists ? (
                <span className="text-xs text-green-500">已添加</span>
              ) : (
                <span className="text-xs text-gray-500">点击添加</span>
              )}
            </button>
          );
        })}
      </div>
      {accounts.length > 0 && (
        <p className="text-xs text-gray-500 mt-4 text-center">账户已设置，刷新页面进入主界面</p>
      )}
    </div>
  );
}
