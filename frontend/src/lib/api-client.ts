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
    update: (tableId: string, colId: string, data: { name?: string; type?: string }) =>
      request<import("@/types").Column>(`/tables/${tableId}/columns/${colId}`, {
        method: "PATCH", body: JSON.stringify(data),
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
  emails: {
    compose: (data: { table_id: string; subject_template: string; body_template: string; personalization_level: string; row_ids?: string[]; ai_instructions?: string }) =>
      request<import("@/types").EmailDraft[]>("/emails/compose", { method: "POST", body: JSON.stringify(data) }),
    drafts: (tableId: string) => request<import("@/types").EmailDraft[]>(`/emails/drafts/${tableId}`),
    updateDraft: (draftId: string, data: { subject?: string; body?: string; status?: string }) =>
      request<import("@/types").EmailDraft>(`/emails/drafts/${draftId}`, { method: "PATCH", body: JSON.stringify(data) }),
    send: (draftIds: string[], delaySeconds?: number) =>
      request<{ sent: number; failed: number; results: unknown[] }>("/emails/send", {
        method: "POST", body: JSON.stringify({ draft_ids: draftIds, delay_seconds: delaySeconds ?? 30 }),
      }),
    testSend: (to: string, subject: string, body: string) =>
      request<{ success: boolean; error: string }>("/emails/test-send", {
        method: "POST", body: JSON.stringify({ to, subject, body }),
      }),
  },
  linkedin: {
    status: () => request<import("@/types").LinkedInStatus>("/linkedin/status"),
    connectCookie: (li_at: string) => request<{ success: boolean }>("/linkedin/connect-cookie", {
      method: "POST", body: JSON.stringify({ li_at }),
    }),
    connectBrowser: () => request<{ success: boolean }>("/linkedin/connect-browser", { method: "POST" }),
    importBrowser: (browser?: string) => request<{ success: boolean }>("/linkedin/import-browser", {
      method: "POST", body: JSON.stringify({ browser: browser || "auto" }),
    }),
    disconnect: () => request<{ success: boolean }>("/linkedin/disconnect", { method: "POST" }),
    search: (query: string, maxResults?: number) => request<{ results: unknown[] }>("/linkedin/search", {
      method: "POST", body: JSON.stringify({ query, max_results: maxResults || 5 }),
    }),
  },
  find: {
    buildList: (data: { criteria: string; target_count: number; entity_type: string; country?: string; table_name?: string }) =>
      request<import("@/types").FindResponse>("/find", {
        method: "POST", body: JSON.stringify(data),
      }),
  },
  csv: {
    import: async (tableId: string, file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`${API_BASE}/api/tables/${tableId}/import-csv`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error("Import failed");
      return res.json() as Promise<{ rows_imported: number; columns: number }>;
    },
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
    exportServer: (tableId: string) => {
      window.open(`${API_BASE}/api/tables/${tableId}/export-csv`, "_blank");
    },
  },
};
