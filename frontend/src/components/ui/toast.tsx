"use client";
import { createContext, useContext, useState, useCallback, useEffect, useRef } from "react";
import { cn } from "@/lib/utils";

type ToastVariant = "success" | "error" | "info";

interface Toast {
  id: string;
  message: string;
  variant: ToastVariant;
  dismissing?: boolean;
}

interface ToastContextValue {
  toast: (message: string, variant?: ToastVariant) => void;
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}

const BORDER_COLORS: Record<ToastVariant, string> = {
  success: "#10b981",
  error: "#ef4444",
  info: "#06b6d4",
};

const ICON: Record<ToastVariant, string> = {
  success: "✓",
  error: "✕",
  info: "ℹ",
};

const ICON_COLOR: Record<ToastVariant, string> = {
  success: "text-emerald-400",
  error: "text-red-400",
  info: "text-[#06b6d4]",
};

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: (id: string) => void }) {
  return (
    <div
      className={cn(
        "relative flex items-start gap-3 px-4 py-3 rounded-xl",
        "glass-panel shadow-2xl min-w-[280px] max-w-[360px]",
        toast.dismissing ? "toast-out" : "toast-in"
      )}
      style={{
        borderLeft: `3px solid ${BORDER_COLORS[toast.variant]}`,
        boxShadow: `0 4px 24px rgba(0,0,0,0.4), 0 0 0 1px rgba(63,63,70,0.4)`,
      }}
    >
      <span className={cn("text-sm font-mono font-bold mt-px shrink-0", ICON_COLOR[toast.variant])}>
        {ICON[toast.variant]}
      </span>
      <p className="text-sm text-[#e4e4e7] leading-snug flex-1">{toast.message}</p>
      <button
        onClick={() => onDismiss(toast.id)}
        className="text-[#52525b] hover:text-[#a1a1aa] transition-colors shrink-0 text-xs mt-0.5"
      >
        ✕
      </button>
    </div>
  );
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timerRefs = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.map((t) => t.id === id ? { ...t, dismissing: true } : t));
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 280);
  }, []);

  const toast = useCallback((message: string, variant: ToastVariant = "info") => {
    const id = Math.random().toString(36).slice(2);
    setToasts((prev) => [...prev, { id, message, variant }]);

    timerRefs.current[id] = setTimeout(() => {
      dismiss(id);
      delete timerRefs.current[id];
    }, 3200);
  }, [dismiss]);

  const success = useCallback((message: string) => toast(message, "success"), [toast]);
  const error = useCallback((message: string) => toast(message, "error"), [toast]);
  const info = useCallback((message: string) => toast(message, "info"), [toast]);

  useEffect(() => {
    return () => {
      Object.values(timerRefs.current).forEach(clearTimeout);
    };
  }, []);

  return (
    <ToastContext.Provider value={{ toast, success, error, info }}>
      {children}
      {/* Toast container */}
      <div
        className="fixed bottom-6 right-6 z-[100] flex flex-col gap-2 items-end pointer-events-none"
        aria-live="polite"
      >
        {toasts.map((t) => (
          <div key={t.id} className="pointer-events-auto">
            <ToastItem toast={t} onDismiss={dismiss} />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
