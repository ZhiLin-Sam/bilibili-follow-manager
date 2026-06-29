import { useState } from "react"
import { Routes, Route, NavLink } from "react-router-dom"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import {
  Download,
  Filter,
  Eye,
  UserX,
  ChevronLeft,
  ChevronRight,
} from "lucide-react"
import { FetchPage } from "@/pages/FetchPage"
import { FilterPage } from "@/pages/FilterPage"
import { ReviewPage } from "@/pages/ReviewPage"
import { UnfollowPage } from "@/pages/UnfollowPage"

type NavItem = {
  id: string
  label: string
  icon: React.ComponentType<{ className?: string }>
  path: string
}

const navItems: NavItem[] = [
  { id: "fetch", label: "拉取", icon: Download, path: "/" },
  { id: "filter", label: "过滤", icon: Filter, path: "/filter" },
  { id: "review", label: "审查", icon: Eye, path: "/review" },
  { id: "unfollow", label: "取关", icon: UserX, path: "/unfollow" },
]

export function App() {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <aside
        className={cn(
          "flex flex-col border-r border-border bg-sidebar transition-all duration-200",
          collapsed ? "w-14" : "w-52",
        )}
      >
        {/* Header */}
        <div className={cn("flex items-center h-14 px-3", collapsed && "justify-center")}>
          {!collapsed && (
            <span className="font-semibold text-sidebar-primary text-sm tracking-wide">
              BiliManager
            </span>
          )}
        </div>
        <Separator />

        {/* Nav */}
        <ScrollArea className="flex-1 px-2 py-2">
          <nav className="flex flex-col gap-1">
            {navItems.map((item) => (
              <NavLink
                key={item.id}
                to={item.path}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                    isActive
                      ? "bg-sidebar-accent text-sidebar-accent-foreground"
                      : "text-sidebar-foreground/60",
                    collapsed && "justify-center px-2",
                  )
                }
              >
                <item.icon className="size-4 shrink-0" />
                {!collapsed && <span>{item.label}</span>}
              </NavLink>
            ))}
          </nav>
        </ScrollArea>

        {/* Footer */}
        <Separator />
        <div className="p-2">
          <Button
            variant="ghost"
            size="icon"
            className="w-full"
            onClick={() => setCollapsed(!collapsed)}
          >
            {collapsed ? (
              <ChevronRight className="size-4" />
            ) : (
              <ChevronLeft className="size-4" />
            )}
          </Button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-hidden">
        <ScrollArea className="h-full">
          <div className="p-6">
            <Routes>
              <Route path="/" element={<FetchPage />} />
              <Route path="/filter" element={<FilterPage />} />
              <Route path="/review" element={<ReviewPage />} />
              <Route path="/unfollow" element={<UnfollowPage />} />
            </Routes>
          </div>
        </ScrollArea>
      </main>
    </div>
  )
}
