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
}

export interface PortfolioSummary {
  accounts: AccountSummary[];
  total_market_value: number;
  total_cost: number;
  total_pnl: number;
  total_pnl_pct: number;
  by_market: Record<string, { market_value: number; count: number; pnl: number; pct: number }>;
  by_position_type: Record<string, { market_value: number; count: number; pct: number }>;
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

export interface SyncLog {
  id: number;
  broker: string;
  status: string;
  message?: string;
  positions_updated: number;
  started_at: string;
  finished_at?: string;
}
