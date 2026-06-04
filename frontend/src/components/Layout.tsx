import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { BookOpen } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

// Three top-level sections, each with its own sub-pages.
const SECTIONS: {
  name: string;
  base: string;
  items: { label: string; to: string }[];
}[] = [
  {
    name: "Portfolio",
    base: "portfolio",
    items: [
      { label: "Portfolio", to: "/" },
      { label: "Watchlist", to: "/watchlist" },
      { label: "Automation", to: "/automation" },
    ],
  },
  {
    name: "AI Analysis",
    base: "ai",
    items: [
      { label: "Analyze", to: "/analyze" },
      { label: "Decisions", to: "/decisions" },
      { label: "Morning", to: "/morning" },
      { label: "Weekly", to: "/weekly" },
      { label: "Memory", to: "/memory" },
    ],
  },
  {
    name: "Backtesting",
    base: "backtest",
    items: [
      { label: "Backtest", to: "/backtest" },
      { label: "Run History", to: "/runs" },
      { label: "Compare", to: "/compare" },
      { label: "Data Cache", to: "/data" },
      { label: "Parameters", to: "/params" },
    ],
  },
];

// Map a pathname to its owning section.
function sectionForPath(path: string): string {
  if (
    path.startsWith("/analyze") ||
    path.startsWith("/decisions") ||
    path.startsWith("/morning") ||
    path.startsWith("/weekly") ||
    path.startsWith("/memory")
  )
    return "AI Analysis";
  if (
    path.startsWith("/backtest") ||
    path.startsWith("/runs") ||
    path.startsWith("/compare") ||
    path.startsWith("/data") ||
    path.startsWith("/params")
  )
    return "Backtesting";
  return "Portfolio";
}

export default function Layout() {
  const { pathname } = useLocation();
  const activeSection = sectionForPath(pathname);
  const section = SECTIONS.find((s) => s.name === activeSection)!;

  const health = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 15000,
  });
  const ok = health.data?.status === "ok";

  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-30 bg-bg-soft/95 backdrop-blur border-b border-line">
        {/* Row 1: brand + section tabs + health */}
        <div className="flex items-center justify-between px-5 h-12">
          <div className="flex items-center gap-6">
            <NavLink to="/" className="flex items-baseline gap-2">
              <span className="text-lg font-extrabold text-brand">Akash</span>
              <span className="text-[11px] text-gray-500 hidden sm:block">
                Research Platform
              </span>
            </NavLink>
            <nav className="flex items-center gap-1">
              {SECTIONS.map((s) => (
                <NavLink
                  key={s.name}
                  to={s.items[0].to}
                  className={cn(
                    "px-3 py-1.5 text-sm font-semibold rounded-lg transition-colors",
                    s.name === activeSection
                      ? "text-brand bg-brand/10"
                      : "text-gray-400 hover:text-gray-200"
                  )}
                >
                  {s.name}
                </NavLink>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-4">
            <NavLink
              to="/guide"
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-1.5 px-2.5 py-1 text-sm font-semibold rounded-lg transition-colors",
                  isActive
                    ? "text-brand bg-brand/10"
                    : "text-gray-400 hover:text-gray-200"
                )
              }
            >
              <BookOpen className="h-4 w-4" />
              <span className="hidden sm:block">Guide</span>
            </NavLink>
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  "h-2 w-2 rounded-full",
                  ok ? "bg-pos" : "bg-neg animate-pulse"
                )}
              />
              <span className="text-xs text-gray-500 hidden sm:block">
                API {health.data?.status ?? "…"}
              </span>
            </div>
          </div>
        </div>
        {/* Row 2: sub-nav for the active section (hidden on the standalone Guide page) */}
        {!pathname.startsWith("/guide") && (
        <div className="flex items-center gap-1 px-5 h-10 bg-bg/40 border-t border-line/50 overflow-x-auto">
          {section.items.map((it) => (
            <NavLink
              key={it.to}
              to={it.to}
              end={it.to === "/"}
              className={({ isActive }) =>
                cn(
                  "px-3 py-1 text-sm rounded-md whitespace-nowrap transition-colors",
                  isActive
                    ? "bg-brand/15 text-brand font-medium"
                    : "text-gray-400 hover:text-gray-200"
                )
              }
            >
              {it.label}
            </NavLink>
          ))}
        </div>
        )}
      </header>

      <main className="flex-1 w-full max-w-7xl mx-auto px-5 py-6">
        <Outlet />
      </main>

      <footer className="border-t border-line px-5 py-3 text-center text-xs text-gray-600">
        Akash Research Platform · AI portfolio manager · local instance
      </footer>
    </div>
  );
}
