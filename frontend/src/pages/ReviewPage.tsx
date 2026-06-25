import { useState, useEffect, useCallback } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import { Search, Check, X, Shield } from "lucide-react"
import { cn } from "@/lib/utils"

const API_BASE = "http://127.0.0.1:9000/api"

type FollowItem = {
  mid: number
  uname: string
  sign: string
  face: string
  mtime: number
  official: string
  vip: string
  follower: number
  archive_count: number
  level: number
  total_view: number
  ff_ratio: number
  spacesta: number
  verdict: string
  rule_keep: string
  rule_delete: string
  delete_score: number
  keep_score: number
}

const verdictColors: Record<string, string> = {
  keep: "bg-green-500/10 text-green-400 border-green-500/20",
  delete: "bg-red-500/10 text-red-400 border-red-500/20",
  unreviewed: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
  protected: "bg-blue-500/10 text-blue-400 border-blue-500/20",
}

const verdictLabels: Record<string, string> = {
  keep: "保留",
  delete: "删除",
  unreviewed: "待审",
  protected: "受保护",
}

export function ReviewPage() {
  const [items, setItems] = useState<FollowItem[]>([])
  const [totalCount, setTotalCount] = useState(0)
  const [search, setSearch] = useState("")
  const [verdictFilter, setVerdictFilter] = useState("all")
  const [sortBy, setSortBy] = useState("delete_score")
  const [sortDir, setSortDir] = useState("desc")
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [loading, setLoading] = useState(false)

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ search, sort_by: sortBy, sort_dir: sortDir })
      if (verdictFilter !== "all") params.set("verdict", verdictFilter)
      const r = await fetch(`${API_BASE}/review/list?${params}`)
      if (r.ok) {
        const data = await r.json()
        setItems(data.items)
        setTotalCount(data.count)
      }
    } catch { /* */ }
    setLoading(false)
  }, [search, verdictFilter, sortBy, sortDir])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const setVerdict = async (mid: number, verdict: string) => {
    try {
      await fetch(`${API_BASE}/review/verdict`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mid, verdict }),
      })
      // In-place update
      setItems(prev =>
        prev.map(item => item.mid === mid ? { ...item, verdict } : item)
      )
    } catch { /* */ }
  }

  const batchVerdict = async (verdict: string) => {
    if (selected.size === 0) return
    try {
      await fetch(`${API_BASE}/review/verdict/batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mids: Array.from(selected), verdict }),
      })
      fetchData()
      setSelected(new Set())
    } catch { /* */ }
  }

  const toggleSort = (col: string) => {
    if (sortBy === col) {
      setSortDir(prev => prev === "asc" ? "desc" : "asc")
    } else {
      setSortBy(col)
      setSortDir("desc")
    }
  }

  const toggleSelect = (mid: number) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(mid)) next.delete(mid); else next.add(mid)
      return next
    })
  }

  const fmtNum = (n: number) => n === -1 ? "—" : n?.toLocaleString?.() ?? "—"

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">审查</h1>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => batchVerdict("keep")} disabled={selected.size === 0}>
            <Check className="size-4 mr-2" />标记保留
          </Button>
          <Button variant="outline" size="sm" onClick={() => batchVerdict("delete")} disabled={selected.size === 0}>
            <X className="size-4 mr-2" />标记删除
          </Button>
          <Button variant="outline" size="sm" onClick={() => batchVerdict("protected")} disabled={selected.size === 0}>
            <Shield className="size-4 mr-2" />保护
          </Button>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="py-3">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
              <Input
                placeholder="搜索 UID / 用户名 / 签名..."
                className="pl-9"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            {[
              ["all", `全部 ${totalCount}`],
              ["keep", "保留"],
              ["delete", "删除"],
              ["unreviewed", "待审"],
              ["protected", "受保护"],
            ].map(([v, label]) => (
              <Badge
                key={v}
                variant={verdictFilter === v ? "default" : "secondary"}
                className="cursor-pointer"
                onClick={() => setVerdictFilter(v)}
              >
                {label}
              </Badge>
            ))}
            <Button variant="ghost" size="sm" onClick={fetchData} disabled={loading}>
              {loading ? "加载中..." : "🔄 刷新"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Data Table */}
      <Card>
        <CardContent className="p-0">
          <div className="overflow-auto max-h-[calc(100vh-320px)]">
          <Table>
            <TableHeader className="sticky top-0 bg-card z-10">
              <TableRow>
                <TableHead className="w-[50px]"></TableHead>
                <TableHead className="w-[90px] cursor-pointer select-none" onClick={() => toggleSort("mid")}>UID {sortBy === "mid" ? (sortDir === "asc" ? "↑" : "↓") : ""}</TableHead>
                <TableHead className="cursor-pointer select-none" onClick={() => toggleSort("uname")}>用户名 {sortBy === "uname" ? (sortDir === "asc" ? "↑" : "↓") : ""}</TableHead>
                <TableHead className="max-w-[180px]">签名</TableHead>
                <TableHead>认证</TableHead>
                <TableHead>VIP</TableHead>
                <TableHead className="text-right cursor-pointer select-none" onClick={() => toggleSort("follower")}>粉丝 {sortBy === "follower" ? (sortDir === "asc" ? "↑" : "↓") : ""}</TableHead>
                <TableHead className="text-right cursor-pointer select-none" onClick={() => toggleSort("archive_count")}>投稿 {sortBy === "archive_count" ? (sortDir === "asc" ? "↑" : "↓") : ""}</TableHead>
                <TableHead className="text-right cursor-pointer select-none" onClick={() => toggleSort("level")}>等级 {sortBy === "level" ? (sortDir === "asc" ? "↑" : "↓") : ""}</TableHead>
                <TableHead className="text-right cursor-pointer select-none" onClick={() => toggleSort("delete_score")}>删除分 {sortBy === "delete_score" ? (sortDir === "asc" ? "↑" : "↓") : ""}</TableHead>
                <TableHead>判定</TableHead>
                <TableHead className="w-[80px]">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.length === 0 && (
                <TableRow>
                  <TableCell colSpan={12} className="text-center text-muted-foreground py-12">
                    {loading ? "加载中..." : "无数据 — 请先在「拉取」页获取关注列表"}
                  </TableCell>
                </TableRow>
              )}
              {items.map((item) => (
                <TableRow key={item.mid} className="group">
                  <TableCell>
                    <input type="checkbox" checked={selected.has(item.mid)} onChange={() => toggleSelect(item.mid)} className="size-4 accent-primary" />
                  </TableCell>
                  <TableCell className="font-mono text-xs">{item.mid}</TableCell>
                  <TableCell className="font-medium">{item.uname}</TableCell>
                  <TableCell className="text-xs text-muted-foreground max-w-[180px] truncate">{item.sign || "—"}</TableCell>
                  <TableCell className="text-xs">{item.official}</TableCell>
                  <TableCell className="text-xs">{item.vip}</TableCell>
                  <TableCell className="text-right text-xs">{fmtNum(item.follower)}</TableCell>
                  <TableCell className="text-right text-xs">{fmtNum(item.archive_count)}</TableCell>
                  <TableCell className="text-right text-xs">{item.level === -1 ? "—" : item.level}</TableCell>
                  <TableCell className="text-right">
                    <Badge variant={item.delete_score > 50 ? "destructive" : "secondary"} className="text-xs">
                      {item.delete_score}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge className={cn("text-xs border", verdictColors[item.verdict] ?? "")}>
                      {verdictLabels[item.verdict] ?? item.verdict}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Button
                        variant="ghost" size="icon" className="size-7 hover:bg-green-500/20 hover:text-green-400"
                        onClick={() => setVerdict(item.mid, "keep")}
                        disabled={item.verdict === "protected"}
                      >
                        <Check className="size-3.5" />
                      </Button>
                      <Button
                        variant="ghost" size="icon" className="size-7 hover:bg-red-500/20 hover:text-red-400"
                        onClick={() => setVerdict(item.mid, "delete")}
                        disabled={item.verdict === "protected"}
                      >
                        <X className="size-3.5" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
