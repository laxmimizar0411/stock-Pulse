import React, { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  Search,
  BarChart3,
  Star,
  Briefcase,
  Newspaper,
  FileText,
  Menu,
  X,
  TrendingUp,
  ChevronRight,
  Bell,
  LineChart,
  Database,
  Server,
  HardDrive,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import SearchDialog from "@/components/SearchDialog";

const navItems = [
  { path: "/", label: "Dashboard", icon: LayoutDashboard },
  { path: "/analyzer", label: "Stock Analyzer", icon: BarChart3 },
  { path: "/screener", label: "Screener", icon: Search },
  { path: "/watchlist", label: "Watchlist", icon: Star },
  { path: "/portfolio", label: "Portfolio", icon: Briefcase },
  { path: "/alerts", label: "Alerts", icon: Bell },
  { path: "/backtest", label: "Backtest", icon: LineChart },
  { path: "/data-pipeline", label: "Data Pipeline", icon: Database },
  { path: "/db-dashboard", label: "DB Dashboard", icon: Server },
  { path: "/pg-control", label: "PG Control", icon: HardDrive },
  { path: "/news", label: "News Hub", icon: Newspaper },
  { path: "/reports", label: "Reports", icon: FileText },
];

export default function Layout({ children }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const location = useLocation();

  return (
    <div className="flex min-h-screen bg-[#09090B]">
      {/* Mobile sidebar backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/80 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 w-64 bg-[#09090B] border-r border-[#27272A] transform transition-transform duration-200 ease-in-out lg:translate-x-0 lg:static lg:inset-auto",
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="flex items-center gap-2 px-6 py-5 border-b border-[#27272A]">
            <TrendingUp className="w-8 h-8 text-[#3B82F6]" />
            <span className="text-2xl font-bold font-heading tracking-tight text-white">
              StockPulse
            </span>
            <Button
              variant="ghost"
              size="icon"
              className="ml-auto lg:hidden"
              onClick={() => setSidebarOpen(false)}
              data-testid="close-sidebar-btn"
            >
              <X className="w-5 h-5" />
            </Button>
          </div>

          {/* Navigation */}
          <ScrollArea className="flex-1 px-3 py-4">
            <nav className="space-y-1">
              {navItems.map((item) => {
                const isActive = location.pathname === item.path;
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    data-testid={`nav-${item.label.toLowerCase().replace(/\s/g, "-")}`}
                    onClick={() => setSidebarOpen(false)}
                    className={cn(
                      "flex items-center gap-3 px-3 py-2.5 rounded-sm text-sm font-medium transition-colors",
                      isActive
                        ? "bg-[#3B82F6]/10 text-[#3B82F6] border-l-2 border-[#3B82F6]"
                        : "text-[#A1A1AA] hover:text-white hover:bg-[#18181B]"
                    )}
                  >
                    <item.icon className="w-5 h-5" />
                    {item.label}
                    {isActive && <ChevronRight className="w-4 h-4 ml-auto" />}
                  </Link>
                );
              })}
            </nav>
          </ScrollArea>

          {/* Footer */}
          <div className="px-4 py-4 border-t border-[#27272A]">
            <div className="text-xs text-[#A1A1AA]">
              <p>Indian Stock Market Analysis</p>
              <p className="mt-1">Data refreshes every 5 min</p>
            </div>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="sticky top-0 z-30 flex items-center gap-4 px-4 py-3 bg-[#09090B]/80 backdrop-blur-md border-b border-[#27272A]">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={() => setSidebarOpen(true)}
            data-testid="open-sidebar-btn"
          >
            <Menu className="w-5 h-5" />
          </Button>

          <Button
            variant="outline"
            className="flex-1 max-w-md justify-start text-[#A1A1AA] hover:text-white"
            onClick={() => setSearchOpen(true)}
            data-testid="search-btn"
          >
            <Search className="w-4 h-4 mr-2" />
            <span>Search stocks...</span>
            <kbd className="ml-auto hidden sm:inline-flex h-5 items-center gap-1 rounded border border-[#27272A] bg-[#18181B] px-1.5 font-mono text-xs text-[#A1A1AA]">
              ⌘K
            </kbd>
          </Button>

          <div className="flex items-center gap-2">
            <div className="hidden sm:flex items-center gap-2 text-sm">
              <span className="text-[#A1A1AA]">Market:</span>
              <span className="text-green-500 font-mono">OPEN</span>
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-auto">
          <div className="container max-w-[1600px] mx-auto px-4 md:px-6 py-6">
            {children}
          </div>
        </main>
      </div>

      {/* Search Dialog */}
      <SearchDialog open={searchOpen} onOpenChange={setSearchOpen} />
    </div>
  );
}
