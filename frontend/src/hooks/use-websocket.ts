"use client";
import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";

interface CellUpdate {
  type: "cell_update";
  cell_id: string;
  value: string | null;
  status: string;
}

export function useWebSocket(tableId: string | undefined) {
  const wsRef = useRef<WebSocket | null>(null);
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!tableId) return;

    const wsUrl = `${(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace("http", "ws")}/ws/${tableId}`;
    const ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
      try {
        const data: CellUpdate = JSON.parse(event.data);
        if (data.type === "cell_update") {
          queryClient.invalidateQueries({ queryKey: ["rows", tableId] });
        }
      } catch {}
    };

    ws.onclose = () => {
      setTimeout(() => {
        if (wsRef.current === ws) {
          wsRef.current = null;
        }
      }, 3000);
    };

    wsRef.current = ws;
    return () => {
      ws.close();
    };
  }, [tableId, queryClient]);
}
