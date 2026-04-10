"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";

interface CellUpdate {
  type: "cell_update";
  cell_id: string;
  column_id: string | null;
  value: string | null;
  status: string;
}

interface EnrichmentLog {
  type: "enrichment_log";
  message: string;
}

type WSMessage = CellUpdate | EnrichmentLog;

const RECONNECT_DELAY_MS = 3000;
const MAX_RECONNECT_ATTEMPTS = 10;
const MAX_LOG_ENTRIES = 100;

export function useWebSocket(tableId: string | undefined) {
  const wsRef = useRef<WebSocket | null>(null);
  const queryClient = useQueryClient();
  const reconnectAttempts = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const unmounted = useRef(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [activeColumnIds, setActiveColumnIds] = useState<Set<string>>(new Set());

  const clearLogs = useCallback(() => setLogs([]), []);

  useEffect(() => {
    if (!tableId) return;
    unmounted.current = false;

    const wsUrl = `${(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace("http", "ws")}/ws/${tableId}`;

    function connect() {
      if (unmounted.current) return;

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        reconnectAttempts.current = 0;
        setIsConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const data: WSMessage = JSON.parse(event.data);
          if (data.type === "cell_update") {
            queryClient.invalidateQueries({ queryKey: ["rows", tableId] });
            // Track which columns have running cells
            if (data.column_id) {
              setActiveColumnIds((prev) => {
                const next = new Set(prev);
                if (data.status === "running" || data.status === "pending") {
                  next.add(data.column_id!);
                }
                return next;
              });
              // Invalidate enrichment status for completed cells
              if (data.status !== "running" && data.status !== "pending") {
                queryClient.invalidateQueries({ queryKey: ["enrich-status", tableId, data.column_id] });
              }
            }
          } else if (data.type === "enrichment_log") {
            setLogs((prev) => [...prev.slice(-(MAX_LOG_ENTRIES - 1)), data.message]);
          }
        } catch {}
      };

      ws.onclose = () => {
        if (unmounted.current) return;
        wsRef.current = null;
        setIsConnected(false);
        if (reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttempts.current += 1;
          reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS);
        }
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    connect();

    return () => {
      unmounted.current = true;
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
        reconnectTimer.current = null;
      }
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [tableId, queryClient]);

  return { logs, clearLogs, isConnected, activeColumnIds };
}
