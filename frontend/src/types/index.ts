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
  tables: Table[];
  total: number;
}
