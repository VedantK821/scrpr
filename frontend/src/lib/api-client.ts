const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}/api${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `API error: ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  tables: {
    list: () => request<import("@/types").TableListResponse>("/tables"),
    get: (id: string) => request<import("@/types").Table>(`/tables/${id}`),
    create: (name: string) => request<import("@/types").Table>("/tables", {
      method: "POST", body: JSON.stringify({ name }),
    }),
    update: (id: string, name: string) => request<import("@/types").Table>(`/tables/${id}`, {
      method: "PATCH", body: JSON.stringify({ name }),
    }),
    delete: (id: string) => request<void>(`/tables/${id}`, { method: "DELETE" }),
  },
  columns: {
    list: (tableId: string) => request<import("@/types").Column[]>(`/tables/${tableId}/columns`),
    create: (tableId: string, data: { name: string; type: string; config?: Record<string, unknown> }) =>
      request<import("@/types").Column>(`/tables/${tableId}/columns`, {
        method: "POST", body: JSON.stringify(data),
      }),
    delete: (tableId: string, colId: string) =>
      request<void>(`/tables/${tableId}/columns/${colId}`, { method: "DELETE" }),
  },
  rows: {
    list: (tableId: string) => request<import("@/types").Row[]>(`/tables/${tableId}/rows`),
    create: (tableId: string, cells?: Record<string, string>) =>
      request<import("@/types").Row>(`/tables/${tableId}/rows`, {
        method: "POST", body: JSON.stringify({ cells }),
      }),
    delete: (tableId: string, rowId: string) =>
      request<void>(`/tables/${tableId}/rows/${rowId}`, { method: "DELETE" }),
  },
  cells: {
    update: (cellId: string, data: { value?: string; status?: string }) =>
      request<import("@/types").Cell>(`/cells/${cellId}`, {
        method: "PATCH", body: JSON.stringify(data),
      }),
  },
  enrichments: {
    trigger: (tableId: string, columnId: string, rowIds?: string[]) =>
      request<{ triggered: number; results: any[] }>(`/tables/${tableId}/columns/${columnId}/enrich`, {
        method: "POST",
        body: JSON.stringify(rowIds ? { row_ids: rowIds } : {}),
      }),
    status: (tableId: string, columnId: string) =>
      request<{ total: number; completed: number; found: number; not_found: number; errors: number; running: number }>(
        `/tables/${tableId}/columns/${columnId}/enrich/status`
      ),
    quota: () => request<Record<string, { used: number; limit: number; remaining: number }>>("/quota"),
  },
  csv: {
    export: async (tableId: string, columns: import("@/types").Column[], rows: import("@/types").Row[]) => {
      const headers = columns.map((c) => c.name);
      const csvRows = rows.map((row) => {
        return columns.map((col) => {
          const cell = row.cells.find((c) => c.column_id === col.id);
          return cell?.value ?? "";
        });
      });
      const csv = [
        headers.join(","),
        ...csvRows.map((r) => r.map((v) => `"${(v ?? "").replace(/"/g, '""')}"`).join(",")),
      ].join("\n");
      const blob = new Blob([csv], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `scrpr-export.csv`;
      a.click();
    },
  },
};
