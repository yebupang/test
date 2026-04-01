"use client";

import { useState } from "react";
import useSWR from "swr";
import {
  Strategy, PositionRule, ComplianceReport, ComplianceItem,
  POSITION_TYPE_OPTIONS,
} from "@/lib/types";
import {
  getStrategies, createStrategy, updateStrategy, deleteStrategy,
  runComplianceCheck, getAlerts,
} from "@/lib/api";
import {
  Plus, ChevronDown, ChevronUp, Play, Trash2,
  CheckCircle, AlertTriangle, XCircle, Edit2, Save, X,
} from "lucide-react";

// ─── 常量 ─────────────────────────────────────────────────

const LEVEL_STYLES = {
  violation: {
    icon: <XCircle size={16} className="text-red-400 shrink-0 mt-0.5" />,
    border: "border-red-800/50 bg-red-900/10",
    badge: "bg-red-900/30 text-red-400",
  },
  warning: {
    icon: <AlertTriangle size={16} className="text-yellow-400 shrink-0 mt-0.5" />,
    border: "border-yellow-800/50 bg-yellow-900/10",
    badge: "bg-yellow-900/30 text-yellow-400",
  },
  info: {
    icon: <CheckCircle size={16} className="text-blue-400 shrink-0 mt-0.5" />,
    border: "border-blue-800/30 bg-blue-900/5",
    badge: "bg-blue-900/30 text-blue-400",
  },
};

const STATUS_BADGE = {
  ok: "bg-green-900/30 text-green-400",
  warning: "bg-yellow-900/30 text-yellow-400",
  violation: "bg-red-900/30 text-red-400",
};

const STATUS_LABEL = { ok: "合规", warning: "需关注", violation: "违规" };

// ─── 空白策略模板 ──────────────────────────────────────────

function emptyRules(): PositionRule[] {
  return POSITION_TYPE_OPTIONS.map((opt) => ({
    position_type: opt.value,
    target_pct: undefined,
    min_pct: undefined,
    max_pct: undefined,
    trigger_condition: "",
    description: "",
  }));
}

// ─── 合规报告卡片 ──────────────────────────────────────────

function ComplianceReportCard({ report }: { report: ComplianceReport }) {
  const [expanded, setExpanded] = useState(true);
  const style = LEVEL_STYLES;

  return (
    <div className="bg-card p-4 mt-3">
      <div
        className="flex items-center justify-between cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">合规检查结果</span>
          <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_BADGE[report.overall_status]}`}>
            {STATUS_LABEL[report.overall_status]}
          </span>
        </div>
        <div className="flex items-center gap-3 text-xs text-gray-500">
          {report.violations > 0 && (
            <span className="text-red-400">{report.violations} 违规</span>
          )}
          {report.warnings > 0 && (
            <span className="text-yellow-400">{report.warnings} 警告</span>
          )}
          <span>{report.infos} 信息</span>
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </div>
      </div>

      {expanded && (
        <div className="mt-3 space-y-2">
          {report.items.map((item, i) => (
            <ComplianceItemCard key={i} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}

function ComplianceItemCard({ item }: { item: ComplianceItem }) {
  const s = LEVEL_STYLES[item.level] || LEVEL_STYLES.info;
  return (
    <div className={`flex gap-2 p-3 rounded-lg border ${s.border}`}>
      {s.icon}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium">{item.title}</p>
        <p className="text-xs text-gray-400 mt-0.5">{item.detail}</p>
        {item.suggested_action && (
          <p className="text-xs text-indigo-400 mt-1">建议：{item.suggested_action}</p>
        )}
        {item.current_value != null && item.target_value != null && (
          <div className="mt-2 flex items-center gap-2 text-xs">
            <span className="text-gray-500">当前</span>
            <span className="font-mono text-white">{item.current_value.toFixed(1)}%</span>
            <span className="text-gray-600">→</span>
            <span className="text-gray-500">目标</span>
            <span className="font-mono text-indigo-300">{item.target_value.toFixed(1)}%</span>
          </div>
        )}
      </div>
      {item.symbol && (
        <span className="text-xs bg-gray-700 text-gray-300 px-1.5 rounded self-start">{item.symbol}</span>
      )}
    </div>
  );
}

// ─── 仓位规则表单行 ────────────────────────────────────────

function RuleRow({
  rule, onChange,
}: {
  rule: PositionRule;
  onChange: (updated: PositionRule) => void;
}) {
  const opt = POSITION_TYPE_OPTIONS.find((o) => o.value === rule.position_type);
  const colorMap: Record<string, string> = {
    purple: "text-purple-400", blue: "text-blue-400", green: "text-green-400",
    yellow: "text-yellow-400", red: "text-red-400",
  };

  const update = (field: keyof PositionRule, val: string | number | undefined) =>
    onChange({ ...rule, [field]: val });

  return (
    <div className="border border-gray-800 rounded-lg p-3">
      {/* 仓位名称 */}
      <div className="flex items-center gap-2 mb-3">
        <span className={`text-sm font-semibold ${colorMap[opt?.color || "blue"]}`}>
          {opt?.label}
        </span>
        <span className="text-xs text-gray-500">{opt?.desc}</span>
      </div>

      {/* 比例设置 */}
      <div className="grid grid-cols-3 gap-2 mb-3">
        {(["target_pct", "min_pct", "max_pct"] as const).map((field) => (
          <div key={field}>
            <label className="text-xs text-gray-500 block mb-1">
              {field === "target_pct" ? "目标%" : field === "min_pct" ? "最小%" : "最大%"}
            </label>
            <input
              type="number"
              min={0}
              max={100}
              step={1}
              placeholder="—"
              value={rule[field] ?? ""}
              onChange={(e) =>
                update(field, e.target.value === "" ? undefined : parseFloat(e.target.value))
              }
              className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm font-mono focus:border-indigo-500 outline-none"
            />
          </div>
        ))}
      </div>

      {/* 触发条件 */}
      <div className="mb-2">
        <label className="text-xs text-gray-500 block mb-1">触发条件（可选）</label>
        <input
          type="text"
          placeholder={`例：标普500下跌超过15%时动用`}
          value={rule.trigger_condition || ""}
          onChange={(e) => update("trigger_condition", e.target.value)}
          className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs focus:border-indigo-500 outline-none text-gray-300"
        />
      </div>

      {/* 备注 */}
      <div>
        <label className="text-xs text-gray-500 block mb-1">说明（可选）</label>
        <input
          type="text"
          placeholder="对该仓位的额外说明..."
          value={rule.description || ""}
          onChange={(e) => update("description", e.target.value)}
          className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs focus:border-indigo-500 outline-none text-gray-300"
        />
      </div>
    </div>
  );
}

// ─── 策略编辑表单 ──────────────────────────────────────────

function StrategyForm({
  initial,
  onSave,
  onCancel,
}: {
  initial?: Strategy;
  onSave: (data: { name: string; description: string; position_rules: PositionRule[] }) => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState(initial?.name || "");
  const [description, setDescription] = useState(initial?.description || "");
  const [rules, setRules] = useState<PositionRule[]>(
    initial?.position_rules.length
      ? initial.position_rules
      : emptyRules()
  );
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    if (!name.trim()) { alert("请填写策略名称"); return; }
    setSaving(true);
    try {
      await onSave({ name, description, position_rules: rules });
    } finally {
      setSaving(false);
    }
  };

  const updateRule = (index: number, updated: PositionRule) => {
    const next = [...rules];
    next[index] = updated;
    setRules(next);
  };

  return (
    <div className="space-y-4">
      {/* 基本信息 */}
      <div>
        <label className="text-xs text-gray-400 block mb-1">策略名称</label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="例：主交易策略 v1"
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:border-indigo-500 outline-none"
        />
      </div>

      <div>
        <label className="text-xs text-gray-400 block mb-1">策略全文</label>
        <p className="text-xs text-gray-600 mb-1">
          用自然语言描述你的完整交易策略，越详细越好。后续 AI 将据此生成智能分析建议。
        </p>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder={`例：
我将仓位分为五类：
1. 抄底仓（50%）：保留在现金/货币基金，仅在大盘大跌时（标普下跌15%以上，或 VIX 超过30）分批动用。
2. 防守仓：配置高股息、低波动资产（REITs、公用事业等），市场不确定时提高比例。
3. 配置仓：长期持有的核心资产，不受短期市场波动影响...
`}
          rows={8}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm font-mono focus:border-indigo-500 outline-none text-gray-300 resize-y"
        />
      </div>

      {/* 仓位比例规则 */}
      <div>
        <p className="text-xs text-gray-400 mb-3">
          仓位比例规则（选填，填写后可自动进行合规检查）
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {rules.map((rule, i) => (
            <RuleRow key={rule.position_type} rule={rule} onChange={(u) => updateRule(i, u)} />
          ))}
        </div>
      </div>

      {/* 操作按钮 */}
      <div className="flex gap-2">
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm"
        >
          <Save size={14} /> {saving ? "保存中..." : "保存策略"}
        </button>
        <button
          onClick={onCancel}
          className="flex items-center gap-1.5 bg-gray-700 hover:bg-gray-600 text-gray-300 px-4 py-2 rounded-lg text-sm"
        >
          <X size={14} /> 取消
        </button>
      </div>
    </div>
  );
}

// ─── 策略卡片 ──────────────────────────────────────────────

function StrategyCard({
  strategy,
  onEdit,
  onDelete,
  onRefresh,
}: {
  strategy: Strategy;
  onEdit: () => void;
  onDelete: () => void;
  onRefresh: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [checking, setChecking] = useState(false);
  const [report, setReport] = useState<ComplianceReport | null>(null);

  const handleCheck = async () => {
    setChecking(true);
    try {
      const r = await runComplianceCheck(strategy.id) as ComplianceReport;
      setReport(r);
      setExpanded(true);
    } catch (e: unknown) {
      alert("检查失败: " + (e as Error).message);
    } finally {
      setChecking(false);
    }
  };

  const statusColor =
    report?.overall_status === "violation" ? "text-red-400" :
    report?.overall_status === "warning" ? "text-yellow-400" :
    report ? "text-green-400" : "text-gray-500";

  return (
    <div className="bg-card p-4">
      {/* 头部 */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-semibold">{strategy.name}</h3>
            <span className="text-xs text-gray-600">v{strategy.version}</span>
            {report && (
              <span className={`text-xs font-medium ${statusColor}`}>
                {STATUS_LABEL[report.overall_status]}
              </span>
            )}
          </div>
          {strategy.description && (
            <p className="text-xs text-gray-500 mt-1 line-clamp-2">{strategy.description}</p>
          )}
        </div>
        <div className="flex gap-1 shrink-0">
          <button
            onClick={handleCheck}
            disabled={checking}
            title="执行合规检查"
            className="flex items-center gap-1 text-xs bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-400 px-2 py-1.5 rounded-lg"
          >
            <Play size={12} /> {checking ? "检查中..." : "合规检查"}
          </button>
          <button onClick={onEdit} className="p-1.5 text-gray-500 hover:text-gray-300 rounded">
            <Edit2 size={14} />
          </button>
          <button onClick={onDelete} className="p-1.5 text-gray-500 hover:text-red-400 rounded">
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      {/* 仓位规则概览 */}
      {strategy.position_rules.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {strategy.position_rules.map((r) => {
            const opt = POSITION_TYPE_OPTIONS.find((o) => o.value === r.position_type);
            const colorMap: Record<string, string> = {
              purple: "bg-purple-900/30 text-purple-400",
              blue: "bg-blue-900/30 text-blue-400",
              green: "bg-green-900/30 text-green-400",
              yellow: "bg-yellow-900/30 text-yellow-400",
              red: "bg-red-900/30 text-red-400",
            };
            const hasValue = r.target_pct != null || r.max_pct != null;
            if (!hasValue) return null;
            return (
              <span
                key={r.position_type}
                className={`text-xs px-2 py-0.5 rounded-full ${colorMap[opt?.color || "blue"]}`}
              >
                {opt?.label} {r.target_pct != null ? `${r.target_pct}%` : `≤${r.max_pct}%`}
              </span>
            );
          })}
        </div>
      )}

      {/* 展开：完整策略文本 */}
      {strategy.description && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-2 text-xs text-gray-600 hover:text-gray-400 flex items-center gap-1"
        >
          {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          {expanded ? "收起" : "查看完整策略"}
        </button>
      )}
      {expanded && strategy.description && (
        <pre className="mt-2 text-xs text-gray-400 bg-gray-800/50 rounded-lg p-3 whitespace-pre-wrap font-sans">
          {strategy.description}
        </pre>
      )}

      {/* 合规报告 */}
      {report && <ComplianceReportCard report={report} />}
    </div>
  );
}

// ─── 主组件 ───────────────────────────────────────────────

export default function StrategyPanel() {
  const { data: strategies = [], mutate } = useSWR<Strategy[]>(
    "/strategies/",
    getStrategies
  );
  const [mode, setMode] = useState<"list" | "create" | "edit">("list");
  const [editTarget, setEditTarget] = useState<Strategy | null>(null);

  const handleCreate = async (data: Parameters<typeof createStrategy>[0]) => {
    await createStrategy(data);
    await mutate();
    setMode("list");
  };

  const handleUpdate = async (data: object) => {
    if (!editTarget) return;
    await updateStrategy(editTarget.id, data);
    await mutate();
    setMode("list");
    setEditTarget(null);
  };

  const handleDelete = async (id: number) => {
    if (!confirm("确认删除此策略？")) return;
    await deleteStrategy(id);
    await mutate();
  };

  const startEdit = (s: Strategy) => {
    setEditTarget(s);
    setMode("edit");
  };

  if (mode === "create") {
    return (
      <div>
        <h2 className="text-sm text-gray-400 mb-4">新建交易策略</h2>
        <StrategyForm onSave={handleCreate} onCancel={() => setMode("list")} />
      </div>
    );
  }

  if (mode === "edit" && editTarget) {
    return (
      <div>
        <h2 className="text-sm text-gray-400 mb-4">编辑策略 — {editTarget.name}</h2>
        <StrategyForm
          initial={editTarget}
          onSave={handleUpdate}
          onCancel={() => { setMode("list"); setEditTarget(null); }}
        />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* 顶部操作栏 */}
      <div className="flex justify-between items-center">
        <p className="text-sm text-gray-400">
          {strategies.length === 0 ? "尚未创建策略" : `共 ${strategies.length} 个策略`}
        </p>
        <button
          onClick={() => setMode("create")}
          className="flex items-center gap-1.5 text-xs bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1.5 rounded-lg"
        >
          <Plus size={14} /> 新建策略
        </button>
      </div>

      {/* 空状态 */}
      {strategies.length === 0 && (
        <div className="bg-card p-8 text-center">
          <p className="text-gray-400 text-sm mb-2">还没有交易策略</p>
          <p className="text-gray-600 text-xs mb-4">
            点击「新建策略」，用自然语言描述你的交易策略。<br />
            随时添加，不必一次性完成。
          </p>
          <button
            onClick={() => setMode("create")}
            className="text-indigo-400 hover:text-indigo-300 text-sm underline"
          >
            立即新建
          </button>
        </div>
      )}

      {/* 策略列表 */}
      {strategies.map((s) => (
        <StrategyCard
          key={s.id}
          strategy={s}
          onEdit={() => startEdit(s)}
          onDelete={() => handleDelete(s.id)}
          onRefresh={mutate}
        />
      ))}
    </div>
  );
}
