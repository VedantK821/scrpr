"use client";
import { useState } from "react";
import { Sidebar } from "./sidebar";
import { Topbar } from "./topbar";

export function AppShell({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden bg-[#09090b]">
      <Sidebar collapsed={collapsed} onCollapse={setCollapsed} />
      <div className="flex flex-col flex-1 min-w-0">
        <Topbar onToggleSidebar={() => setCollapsed((v) => !v)} sidebarCollapsed={collapsed} />
        <main className="flex-1 overflow-auto relative main-content page-fade-in">
          {children}
        </main>
      </div>
    </div>
  );
}
