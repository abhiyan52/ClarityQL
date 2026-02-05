// API Types

export interface Metric {
  function: "sum" | "count" | "count_distinct" | "avg" | "min" | "max";
  field: string;
  alias?: string;
}

export interface Dimension {
  field: string;
  alias?: string;
}

export interface Filter {
  field: string;
  operator: string;
  value: unknown;
}

export interface OrderBy {
  field: string;
  direction: "asc" | "desc";
}

export interface QueryAST {
  metrics: Metric[];
  dimensions: Dimension[];
  filters: Filter[];
  order_by: OrderBy[];
  limit: number;
}

export interface QueryExplanation {
  aggregates: string[];
  group_by: string[];
  filters: string[];
  order_by: string[];
  limit: number | null;
  source_tables: string[];
  natural_language?: string | null;
}

export interface QueryResult {
  columns: string[];
  rows: Record<string, unknown>[];
  rowCount: number;
}

export interface NLQResponse {
  conversation_id: string;
  ast: QueryAST;
  explainability: QueryExplanation;
  visualization: VisualizationSpec;
  sql: string;
  columns: string[];
  rows: Array<Array<string | number>>;
  intent?: "refine" | "reset";
  merged?: boolean;
}

// Chat Types

export type MessageRole = "user" | "assistant" | "system";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: Date;
  response?: NLQResponse;
  isLoading?: boolean;
}

export interface Conversation {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: Date;
  updatedAt: Date;
}

// Chart Types

export type ChartType = "bar" | "line" | "pie" | "area";

export interface ChartConfig {
  type: ChartType;
  xAxis?: string;
  yAxis?: string;
  colorBy?: string;
}

// Visualization Types (backend-driven)

export type VisualizationType = "table" | "bar" | "line" | "multi-line" | "kpi";

export interface VisualizationSpec {
  type: VisualizationType;
  x: string | null;
  y: string | null;
  series: string | null;
}
