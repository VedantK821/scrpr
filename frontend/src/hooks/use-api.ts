"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";

export function useTables() {
  return useQuery({ queryKey: ["tables"], queryFn: api.tables.list });
}
export function useTable(id: string) {
  return useQuery({ queryKey: ["table", id], queryFn: () => api.tables.get(id) });
}
export function useColumns(tableId: string) {
  return useQuery({ queryKey: ["columns", tableId], queryFn: () => api.columns.list(tableId) });
}
export function useRows(tableId: string) {
  return useQuery({ queryKey: ["rows", tableId], queryFn: () => api.rows.list(tableId) });
}
export function useCreateTable() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => api.tables.create(name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tables"] }),
  });
}
export function useUpdateTable() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => api.tables.update(id, name),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: ["tables"] });
      qc.invalidateQueries({ queryKey: ["table", id] });
    },
  });
}
export function useDeleteTable() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.tables.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tables"] }),
  });
}
export function useCreateColumn(tableId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { name: string; type: string; config?: Record<string, unknown> }) => api.columns.create(tableId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["columns", tableId] }),
  });
}
export function useDeleteColumn(tableId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (colId: string) => api.columns.delete(tableId, colId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["columns", tableId] });
      qc.invalidateQueries({ queryKey: ["rows", tableId] });
    },
  });
}
export function useUpdateColumn(tableId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ colId, data }: { colId: string; data: { name?: string; type?: string } }) =>
      api.columns.update(tableId, colId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["columns", tableId] }),
  });
}
export function useCreateRow(tableId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (cells?: Record<string, string>) => api.rows.create(tableId, cells),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rows", tableId] }),
  });
}
export function useDeleteRow(tableId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (rowId: string) => api.rows.delete(tableId, rowId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rows", tableId] }),
  });
}
