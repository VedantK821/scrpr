export type CellStatus = "empty" | "pending" | "running" | "found" | "not_found" | "error" | "review";
export type ColumnType = "text" | "url" | "checkbox" | "select" | "multi_select" | "number" | "date" | "currency" | "email" | "agent" | "waterfall" | "formula" | "http_api";

export interface Table {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
}

export interface Column {
  id: string;
  table_id: string;
  name: string;
  type: ColumnType;
  position: number;
  config: Record<string, unknown> | null;
}

export interface Cell {
  id: string;
  row_id: string;
  column_id: string;
  value: string | null;
  status: CellStatus;
  updated_at: string;
}

export interface Row {
  id: string;
  table_id: string;
  created_at: string;
  cells: Cell[];
}

export interface TableListResponse {
  items: Table[];
  total: number;
}

export interface EmailDraft {
  id: string;
  row_id: string;
  to_email: string;
  subject: string;
  body: string;
  personalization_level: string;
  confidence: number | null;
  status: string;
}

export interface LinkedInStatus {
  connected: boolean;
  has_cookie: boolean;
}

export interface FindResponse {
  table_id: string;
  table_name: string;
  entities_found: number;
  fields: string[];
}
