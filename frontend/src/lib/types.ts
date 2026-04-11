export type Market = "US" | "HK" | "A";
export type PositionType =
  | "bottom_fishing"   // 抄底仓
  | "defensive"        // 防守仓
  | "allocation"       // 配置仓
  | "volatile"         // 波动仓
  | "speculative"      // 投机仓
  | "unclassified";    // 未分类

export const POSITION_TYPE_LABELS: Record<string, string> = {
  bottom_fishing: "抄底",
  defensive: "防守",
  allocation: "配置",
  volatile: "波动",
  speculative: "投机",
  unclassified: "未分类",
};

export const POSITION_TYPE_COLORS: Record<string, string> = {
  bottom_fishing: "bg-purple-100 text-purple-700",
  defensive: "bg-blue-100 text-blue-700",
  allocation: "bg-green-100 text-green-700",
  volatile: "bg-yellow-100 text-yellow-700",
  speculative: "bg-red-100 text-red-700",
  unclassified: "bg-gray-100 text-gray-500",
};

export const MARKET_LABELS: Record<Market, string> = {
  US: "美股",
  HK: "港股",
  A: "A股",
};

export interface Account {
  id: number;
  name: string;
  broker: string;
  market: string;
  account_id?: string;
  currency: string;
  is_active: boolean;
  cash_balance: number;
  cash_currency: string;
  last_synced_at?: string;
  created_at: string;
}

export interface Position {
  id: number;
  account_id: number;
  symbol: string;
  name?: string;
  market: Market;
  currency: string;
  quantity: number;
  cost_price: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  open_price?: number;
  high_price?: number;
  low_price?: number;
  prev_close?: number;
  change_pct?: number;
  volume?: number;
  pe_ratio?: number;
  pb_ratio?: number;
  dividend_yield?: number;
  market_cap?: number;
  week_52_high?: number;
  week_52_low?: number;
  beta?: number;
  position_type?: PositionType;
  updated_at?: string;
}

export interface AccountSummary {
  account: Account;
  positions: Position[];
  total_market_value: number;
  total_cost: number;
  total_pnl: number;
  total_pnl_pct: number;
  cash_balance: number;
  cash_currency: string;
  total_assets: number;
  equity_ratio: number;
  total_assets_cny: number;
}

export interface PortfolioSummary {
  accounts: AccountSummary[];
  total_market_value: number;
  total_cost: number;
  total_pnl: number;
  total_pnl_pct: number;
  total_cash: number;
  total_assets: number;
  equity_ratio: number;
  total_market_value_cny: number;
  total_cost_cny: number;
  total_pnl_cny: number;
  total_cash_cny: number;
  total_assets_cny: number;
  exchange_rates: Record<string, number>;
  by_market: Record<string, { market_value: number; market_value_cny: number; count: number; pnl: number; pnl_cny: number; pct: number }>;
  by_position_type: Record<string, { market_value: number; market_value_cny: number; count: number; pct: number }>;
}

export interface WatchListItem {
  id: number;
  symbol: string;
  name?: string;
  market: Market;
  currency?: string;
  current_price?: number;
  change_pct?: number;
  pe_ratio?: number;
  pb_ratio?: number;
  dividend_yield?: number;
  week_52_high?: number;
  week_52_low?: number;
  tags?: string;
  note?: string;
  target_price?: number;
  stop_loss_price?: number;
  updated_at?: string;
}

// ─── Strategy ─────────────────────────────────────────────

export const POSITION_TYPE_OPTIONS = [
  { value: "bottom_fishing", label: "抄底仓", color: "purple", desc: "大跌时抄底用" },
  { value: "defensive",      label: "防守仓", color: "blue",   desc: "防御性资产" },
  { value: "allocation",     label: "配置仓", color: "green",  desc: "长期核心持仓" },
  { value: "volatile",       label: "波动仓", color: "yellow", desc: "中期趋势机会" },
  { value: "speculative",    label: "投机仓", color: "red",    desc: "短期博弈/事件驱动" },
] as const;

export interface PositionRule {
  id?: number;
  strategy_id?: number;
  position_type: string;
  target_pct?: number;
  min_pct?: number;
  max_pct?: number;
  trigger_condition?: string;
  description?: string;
}

export interface Strategy {
  id: number;
  name: string;
  description?: string;
  is_active: boolean;
  version: number;
  parsed_rules?: unknown;
  position_rules: PositionRule[];
  created_at: string;
  updated_at: string;
}

export interface ComplianceItem {
  level: "info" | "warning" | "violation";
  category: string;
  title: string;
  detail: string;
  symbol?: string;
  current_value?: number;
  target_value?: number;
  suggested_action?: string;
}

export interface ComplianceReport {
  strategy_id: number;
  strategy_name: string;
  checked_at: string;
  total_market_value: number;
  items: ComplianceItem[];
  violations: number;
  warnings: number;
  infos: number;
  overall_status: "ok" | "warning" | "violation";
}

export interface StrategyAlert {
  id: number;
  strategy_id: number;
  level: string;
  category?: string;
  title: string;
  detail?: string;
  symbol?: string;
  is_read: boolean;
  created_at: string;
}

export interface SyncLog {
  id: number;
  broker: string;
  status: string;
  message?: string;
  positions_updated: number;
  started_at: string;
  finished_at?: string;
}
