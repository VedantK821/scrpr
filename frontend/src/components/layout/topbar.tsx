"use client";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { useTables } from "@/hooks/use-api";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { cn } from "@/lib/utils";

interface TopbarProps {
  onToggleSidebar: () => void;
  sidebarCollapsed: boolean;
}

export function Topbar({ onToggleSidebar, sidebarCollapsed }: TopbarProps) {
  const pathname = usePathname();
  const { data } = useTables();
  const { data: linkedInStatus } = useQuery({
    queryKey: ["linkedin-status"],
    queryFn: api.linkedin.status,
    staleTime: 60_000,
  });
  const liConnected = linkedInStatus?.connected ?? false;

  // Build breadcrumb
  const tableId = pathname?.match(/\/table\/([^/]+)/)?.[1] ?? null;
  const isEmailPage = pathname?.includes("/emails") ?? false;
  const activeTable = data?.items.find((t) => t.id === tableId);

  return (
    <header className="flex items-center gap-3 px-4 h-11 border-b border-[#27272a] bg-[#09090b]/90 backdrop-blur-sm shrink-0 z-20 relative">
      {/* Subtle bottom glow line */}
      <div className="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-[#3f3f46]/60 to-transparent pointer-events-none" />

      {/* Sidebar toggle */}
      <button
        onClick={onToggleSidebar}
        className="flex items-center justify-center w-7 h-7 rounded-md text-[#52525b] hover:text-[#a1a1aa] hover:bg-[#27272a] transition-all border border-transparent hover:border-[#3f3f46]"
        title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect x="1" y="2" width="12" height="1.5" rx="0.75" fill="currentColor" />
          <rect x="1" y="6.25" width="8" height="1.5" rx="0.75" fill="currentColor" />
          <rect x="1" y="10.5" width="12" height="1.5" rx="0.75" fill="currentColor" />
        </svg>
      </button>

      {/* Subtle separator */}
      <div className="h-4 w-px bg-[#27272a]" />

      {/* Breadcrumb */}
      <nav className="flex items-center gap-1.5 text-sm">
        <Link href="/" className="text-[#52525b] hover:text-[#a1a1aa] font-mono transition-colors text-xs">
          Home
        </Link>
        {tableId && activeTable && (
          <>
            <span className="text-[#27272a] text-xs">/</span>
            <Link
              href={`/table/${tableId}`}
              className={cn(
                "font-mono text-xs transition-colors",
                isEmailPage ? "text-[#52525b] hover:text-[#a1a1aa]" : "text-[#a1a1aa] hover:text-[#fafafa]"
              )}
            >
              {activeTable.name}
            </Link>
          </>
        )}
        {isEmailPage && (
          <>
            <span className="text-[#27272a] text-xs">/</span>
            <span className="font-mono text-xs text-[#a1a1aa]">Emails</span>
          </>
        )}
      </nav>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Right actions */}
      <div className="flex items-center gap-1">
        {/* LinkedIn status indicator */}
        <div
          className="flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-mono text-[#52525b] border border-transparent"
          title={liConnected ? "LinkedIn: Connected" : "LinkedIn: Not Connected"}
        >
          <span
            className={cn(
              "w-1.5 h-1.5 rounded-full shrink-0",
              liConnected ? "bg-emerald-400" : "bg-[#3f3f46]"
            )}
            style={liConnected ? { boxShadow: "0 0 5px rgba(52,211,153,0.7)" } : undefined}
          />
          <span className="hidden sm:inline">in</span>
        </div>

        {/* Command palette hint */}
        <button className="flex items-center gap-1.5 px-2 py-1 rounded-md text-[#52525b] hover:text-[#a1a1aa] hover:bg-[#27272a] transition-all text-xs font-mono border border-[#27272a] hover:border-[#3f3f46]">
          <span>⌘K</span>
        </button>

        {/* Settings — links to /settings */}
        <Link
          href="/settings"
          className={cn(
            "flex items-center justify-center w-7 h-7 rounded-md transition-all border border-transparent hover:border-[#27272a]",
            pathname === "/settings"
              ? "text-[#06b6d4] bg-[#06b6d4]/10 border-[#06b6d4]/20"
              : "text-[#52525b] hover:text-[#a1a1aa] hover:bg-[#27272a]"
          )}
          title="Settings"
        >
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path
              d="M6.5 8.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM10.8 7.5a4.4 4.4 0 0 0 .04-.5 4.4 4.4 0 0 0-.04-.5l1.07-.84a.25.25 0 0 0 .06-.33l-1-1.73a.25.25 0 0 0-.31-.11l-1.26.5a3.9 3.9 0 0 0-.87-.5l-.19-1.34a.24.24 0 0 0-.25-.2h-2a.24.24 0 0 0-.25.2l-.19 1.34c-.3.13-.6.3-.87.5l-1.26-.5a.24.24 0 0 0-.31.11l-1 1.73a.24.24 0 0 0 .06.33l1.07.84A4.4 4.4 0 0 0 3 7c0 .17.01.34.04.5L1.97 8.34a.25.25 0 0 0-.06.33l1 1.73a.25.25 0 0 0 .31.11l1.26-.5c.27.2.57.37.87.5l.19 1.34c.04.12.14.2.25.2h2c.11 0 .21-.08.25-.2l.19-1.34c.3-.13.6-.3.87-.5l1.26.5a.24.24 0 0 0 .31-.11l1-1.73a.24.24 0 0 0-.06-.33L10.8 7.5Z"
              fill="currentColor"
            />
          </svg>
        </Link>
      </div>
    </header>
  );
}
