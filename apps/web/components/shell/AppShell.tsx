import * as React from "react";
import { Topbar } from "./Topbar";
import { MobileNav, Sidebar } from "./Sidebar";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="texture-grain flex min-h-screen flex-col bg-canvas">
      <Topbar />
      <MobileNav />
      <div className="mx-auto flex min-h-0 w-full max-w-[1440px] flex-1 gap-2 px-2 pb-6 sm:px-4 lg:px-6">
        <Sidebar />
        <main className="min-w-0 flex-1 rounded-2xl py-5 sm:px-2 lg:py-6">
          {children}
        </main>
      </div>
    </div>
  );
}
