"use client";

import { useState } from "react";
import useSWR from "swr";
import { getAccounts, getPortfolioSummary } from "@/lib/api";
import { Account, PortfolioSummary } from "@/lib/types";
import PortfolioOverview from "@/components/PortfolioOverview";
import PositionTable from "@/components/PositionTable";
import SyncPanel from "@/components/SyncPanel";
import WatchlistPanel from "@/components/WatchlistPanel";
import AccountSetup from "@/components/AccountSetup";
import { LayoutDashboard, List, RefreshCw, Star, Settings } from "lucide-react";

type Tab = "overview" | "positions" | "sync" | "watchlist";

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: "overview", label: "总览", icon: <LayoutDashboard size={20} /> },
  { id: "positions", label: "持仓", icon: <List size={20} /> },
  { id: "sync", label: "同步", icon: <RefreshCw size={20} /> },
  { id: "watchlist", label: "关注", icon: <Star size={20} /> },
];

export default function Home() {
  const [tab, setTab] = useState<Tab>("overview");
  const [setupOpen, setSetupOpen] = useState(false);

  const { data: accounts = [], mutate: refreshAccounts } = useSWR<Account[]>(
    "/accounts/",
    getAccounts,
    { refreshInterval: 0 }
  );

  const { data: summary, mutate: refreshSummary, isLoading } = useSWR<PortfolioSummary>(
    accounts.length > 0 ? "/portfolio/summary" : null,
    getPortfolioSummary,
    { refreshInterval: 60_000 }
  );

  const allPositions = summary?.accounts.flatMap((a) => a.positions) ?? [];
  const hasAccounts = accounts.length > 0;

  return (
    <div className="min-h-screen flex flex-col">
      {/* 顶部导航 */}
      <header className="sticky top-0 z-10 bg-gray-950/95 backdrop-blur border-b border-gray-800">
        <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-lg font-bold text-white">投资助手</span>
            <span className="text-xs text-gray-500 bg-gray-800 px-2 py-0.5 rounded">Beta</span>
          </div>
          <div className="flex items-center gap-2">
            {summary && (
              <span className="hidden md:block text-xs text-gray-500">
                最后更新 {new Date().toLocaleTimeString("zh-CN")}
              </span>
            )}
            <button
              onClick={() => setSetupOpen(!setupOpen)}
              className="p-2 text-gray-400 hover:text-gray-200"
            >
              <Settings size={18} />
            </button>
          </div>
        </div>
      </header>

      {/* 账户设置面板 */}
      {(setupOpen || !hasAccounts) && (
        <div className="max-w-5xl mx-auto px-4 w-full">
          <AccountSetup
            accounts={accounts}
            onCreated={() => { refreshAccounts(); if (!hasAccounts) setSetupOpen(false); }}
          />
          {hasAccounts && (
            <button
              onClick={() => setSetupOpen(false)}
              className="mt-3 text-xs text-gray-500 hover:text-gray-300 block mx-auto"
            >
              关闭设置
            </button>
          )}
        </div>
      )}

      {/* 主内容 */}
      {hasAccounts && !setupOpen && (
        <main className="flex-1 max-w-5xl mx-auto px-4 py-4 pb-24 w-full">
          {isLoading ? (
            <div className="flex items-center justify-center h-40 text-gray-500">
              <RefreshCw size={20} className="animate-spin mr-2" /> 加载中...
            </div>
          ) : (
            <>
              {tab === "overview" && summary && (
                <PortfolioOverview data={summary} />
              )}
              {tab === "overview" && !summary && (
                <div className="bg-card p-8 text-center text-gray-400">
                  <p className="mb-3">暂无持仓数据</p>
                  <button
                    onClick={() => setTab("sync")}
                    className="text-indigo-400 hover:text-indigo-300 text-sm underline"
                  >
                    前往同步数据
                  </button>
                </div>
              )}
              {tab === "positions" && (
                <div className="bg-card p-4">
                  <h2 className="text-sm text-gray-400 mb-4">
                    全部持仓 · 共 {allPositions.length} 只
                  </h2>
                  <PositionTable positions={allPositions} onUpdated={refreshSummary} />
                </div>
              )}
              {tab === "sync" && (
                <div className="bg-card p-4">
                  <h2 className="text-sm text-gray-400 mb-4">数据同步</h2>
                  <SyncPanel accounts={accounts} onSynced={refreshSummary} />
                </div>
              )}
              {tab === "watchlist" && (
                <div className="bg-card p-4">
                  <h2 className="text-sm text-gray-400 mb-4">关注列表</h2>
                  <WatchlistPanel />
                </div>
              )}
            </>
          )}
        </main>
      )}

      {/* 底部导航栏（移动端） */}
      {hasAccounts && !setupOpen && (
        <nav className="fixed bottom-0 left-0 right-0 z-10 bg-gray-950/95 backdrop-blur border-t border-gray-800 md:hidden">
          <div className="grid grid-cols-4 h-16">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`flex flex-col items-center justify-center gap-1 transition-colors ${
                  tab === t.id ? "text-indigo-400" : "text-gray-500"
                }`}
              >
                {t.icon}
                <span className="text-xs">{t.label}</span>
              </button>
            ))}
          </div>
        </nav>
      )}

      {/* 桌面端侧边/顶部 Tab（md 以上） */}
      {hasAccounts && !setupOpen && (
        <div className="hidden md:flex fixed top-14 left-4 flex-col gap-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
                tab === t.id
                  ? "bg-indigo-600 text-white"
                  : "text-gray-400 hover:bg-gray-800"
              }`}
            >
              {t.icon} {t.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
