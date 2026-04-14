"use client";

import { useState, useRef } from "react";
import { syncFutu, syncIB, syncMock, syncCSV, syncPDF, syncImage, refreshQuotes, getSyncLogs } from "@/lib/api";
import { SyncLog } from "@/lib/types";
import useSWR from "swr";
import { RefreshCw, Upload, Wifi, WifiOff } from "lucide-react";

interface Props {
  accounts: { id: number; name: string; broker: string }[];
  onSynced: () => void;
}

export default function SyncPanel({ accounts, onSynced }: Props) {
  const [loading, setLoading] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const { data: logs, mutate: refreshLogs } = useSWR<SyncLog[]>(
    "/sync/logs",
    getSyncLogs,
    { refreshInterval: 0 }
  );

  const withLoading = async (key: string, fn: () => Promise<unknown>) => {
    setLoading(key);
    setMessage(null);
    try {
      const r = await fn() as { message?: string; positions_updated?: number };
      setMessage(r.message || `完成，更新 ${r.positions_updated ?? 0} 条持仓`);
      await refreshLogs();
      onSynced();
    } catch (e: unknown) {
      setMessage(`失败: ${(e as Error).message}`);
    } finally {
      setLoading(null);
    }
  };

  const futuAccount = accounts.find((a) => a.broker === "futu");
  const ibAccount = accounts.find((a) => a.broker === "ib");
  const csvAccount = accounts.find((a) => a.broker === "csv" || a.broker === "ths");
  const mockAccount = accounts.find((a) => a.broker === "mock") || accounts[0];

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !csvAccount) return;
    const name = file.name.toLowerCase();
    const isPDF = name.endsWith(".pdf");
    const isImage = /\.(jpe?g|png|webp|gif)$/.test(name);
    await withLoading("csv", () => {
      if (isPDF) return syncPDF(csvAccount.id, file);
      if (isImage) return syncImage(csvAccount.id, file);
      return syncCSV(csvAccount.id, file);
    });
    if (fileRef.current) fileRef.current.value = "";
  };

  return (
    <div className="space-y-4">
      {/* 同步按钮 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <SyncBtn
          label="富途同步"
          sub="港股+美股"
          icon={<Wifi size={16} />}
          loading={loading === "futu"}
          disabled={!futuAccount}
          onClick={() => withLoading("futu", () => syncFutu(futuAccount!.id))}
          color="indigo"
        />
        <SyncBtn
          label="盈透同步"
          sub="美股"
          icon={<Wifi size={16} />}
          loading={loading === "ib"}
          disabled={!ibAccount}
          onClick={() => withLoading("ib", () => syncIB(ibAccount!.id))}
          color="violet"
        />
        <SyncBtn
          label="A股导入"
          sub="CSV / PDF / 截图"
          icon={<Upload size={16} />}
          loading={loading === "csv"}
          disabled={!csvAccount}
          onClick={() => fileRef.current?.click()}
          color="pink"
        />
        <SyncBtn
          label="刷新行情"
          sub="AKShare"
          icon={<RefreshCw size={16} />}
          loading={loading === "quotes"}
          onClick={() => withLoading("quotes", () => refreshQuotes())}
          color="emerald"
        />
      </div>

      {/* 模拟数据按钮（开发用） */}
      {mockAccount && (
        <button
          onClick={() => withLoading("mock", () => syncMock(mockAccount.id))}
          disabled={loading !== null}
          className="text-xs text-gray-500 hover:text-gray-300 underline"
        >
          {loading === "mock" ? "加载中..." : "加载模拟数据（测试用）"}
        </button>
      )}

      {/* 隐藏的文件上传 */}
      <input ref={fileRef} type="file" accept=".csv,.pdf,.jpg,.jpeg,.png,.webp" className="hidden" onChange={handleFile} />

      {/* 状态消息 */}
      {message && (
        <div className={`text-xs px-3 py-2 rounded-lg ${
          message.startsWith("失败") ? "bg-red-900/30 text-red-400" : "bg-green-900/30 text-green-400"
        }`}>
          {message}
        </div>
      )}

      {/* 同步日志 */}
      {logs && logs.length > 0 && (
        <div>
          <p className="text-xs text-gray-500 mb-2">最近同步记录</p>
          <div className="space-y-1">
            {logs.slice(0, 5).map((log) => (
              <div key={log.id} className="flex items-center gap-2 text-xs text-gray-400">
                <span className={`w-1.5 h-1.5 rounded-full ${
                  log.status === "success" ? "bg-green-500" :
                  log.status === "failed" ? "bg-red-500" : "bg-yellow-500"
                }`} />
                <span className="text-gray-500">{log.broker}</span>
                <span>{log.message}</span>
                <span className="ml-auto text-gray-600">
                  {new Date(log.started_at).toLocaleTimeString("zh-CN")}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function SyncBtn({
  label, sub, icon, loading, disabled, onClick, color,
}: {
  label: string; sub: string; icon: React.ReactNode;
  loading: boolean; disabled?: boolean; onClick: () => void; color: string;
}) {
  const colors: Record<string, string> = {
    indigo: "bg-indigo-600 hover:bg-indigo-500",
    violet: "bg-violet-600 hover:bg-violet-500",
    pink: "bg-pink-600 hover:bg-pink-500",
    emerald: "bg-emerald-700 hover:bg-emerald-600",
  };
  return (
    <button
      onClick={onClick}
      disabled={disabled || loading}
      className={`flex flex-col items-center justify-center gap-1 p-3 rounded-xl text-white transition-colors ${
        disabled ? "opacity-40 cursor-not-allowed bg-gray-700" : colors[color]
      } ${loading ? "animate-pulse" : ""}`}
    >
      {loading ? <RefreshCw size={16} className="animate-spin" /> : icon}
      <span className="text-sm font-medium">{label}</span>
      <span className="text-xs opacity-70">{sub}</span>
    </button>
  );
}
