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
};
