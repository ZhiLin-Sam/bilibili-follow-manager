import { useState, useEffect, useCallback } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel,
  AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Progress } from "@/components/ui/progress"
import { UserX, AlertTriangle, Trash2, Square } from "lucide-react"

const API_BASE = "http://127.0.0.1:9000/api"

type UnfollowItem = { mid: number; uname: string }

export function UnfollowPage() {
  const [items, setItems] = useState<UnfollowItem[]>([])
  const [confirmText, setConfirmText] = useState("")
  const [executing, setExecuting] = useState(false)
  const [result, setResult] = useState("")
  const [progress, setProgress] = useState(0)

  const fetchList = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/unfollow/list`)
      if (r.ok) {
        const data = await r.json()
        setItems(data.items)
      }
    } catch { /* */ }
  }, [])

  useEffect(() => {
    fetchList()
  }, [fetchList])

  const execute = async () => {
    if (confirmText !== "DELETE" || executing) return
    setExecuting(true)
    setProgress(0)
    setResult("")
    try {
      const r = await fetch(`${API_BASE}/unfollow/execute`, { method: "POST" })
      const data = await r.json()
      setResult(`成功: ${data.success}, 失败: ${data.fail}, 总计: ${data.total}`)
      setProgress(100)
      setExecuting(false)
      setConfirmText("")
      await fetchList()
    } catch {
      setResult("执行失败")
      setExecuting(false)
    }
  }

  const stopExecute = async () => {
    await fetch(`${API_BASE}/unfollow/stop`, { method: "POST" })
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">取消关注</h1>
        <Badge variant="destructive" className="text-sm">
          待取关 {items.length} 个
        </Badge>
      </div>

      <div className="grid grid-cols-5 gap-6">
        {/* Left: List */}
        <Card className="col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <UserX className="size-4" />
              待取关名单
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <ScrollArea className="h-[420px]">
              <div className="p-4 space-y-1">
                {items.length === 0 && (
                  <p className="text-sm text-muted-foreground text-center py-8">
                    暂无待取关账号。请先在「审查」页标记删除。
                  </p>
                )}
                {items.map((item) => (
                  <div
                    key={item.mid}
                    className="flex items-center justify-between rounded-md px-3 py-2 text-sm hover:bg-accent"
                  >
                    <span className="font-mono text-xs text-muted-foreground">{item.mid}</span>
                    <span className="font-medium">{item.uname}</span>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>

        {/* Right: Action Panel */}
        <Card className="col-span-3">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <AlertTriangle className="size-4 text-yellow-400" />
              操作面板
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Step 1: Confirmation */}
            <div className="space-y-3">
              <h3 className="text-sm font-medium">1. 确认数量</h3>
              <p className="text-sm text-muted-foreground">
                即将取消关注 <Badge variant="destructive">{items.length}</Badge> 个账号。此操作不可撤销。
              </p>
              {items.length > 0 && (
                <Button variant="outline" onClick={() => {}} disabled>
                  确认（已加载）
                </Button>
              )}
            </div>

            <Separator />

            {/* Step 2: List Review */}
            <div className="space-y-3">
              <h3 className="text-sm font-medium">2. 复核名单</h3>
              <ScrollArea className="h-[120px] rounded-md border p-3">
                <pre className="text-xs text-muted-foreground">
                  {items.map((u) => `${u.mid}|${u.uname}`).join("\n") || "无"}
                </pre>
              </ScrollArea>
            </div>

            <Separator />

            {/* Step 3: Final Confirm */}
            <div className="space-y-3">
              <h3 className="text-sm font-medium">3. 最终确认</h3>
              <p className="text-sm text-muted-foreground">
                请输入 <code className="bg-muted px-1.5 py-0.5 rounded text-xs font-mono">DELETE</code> 以确认执行
              </p>
              <Input
                placeholder="输入 DELETE"
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                className="max-w-[200px] font-mono"
                disabled={executing || items.length === 0}
              />

              <div className="flex items-center gap-2">
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button variant="destructive" disabled={confirmText !== "DELETE" || executing}>
                      <Trash2 className="size-4 mr-2" />
                      执行取消关注
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>最终确认</AlertDialogTitle>
                      <AlertDialogDescription>
                        即将取消关注 {items.length} 个账号。此操作不可撤销！
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>取消</AlertDialogCancel>
                      <AlertDialogAction className="bg-destructive text-destructive-foreground hover:bg-destructive/90" onClick={execute}>
                        确认执行
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>

                <Button variant="secondary" onClick={stopExecute} disabled={!executing}>
                  <Square className="size-4 mr-2" />停止
                </Button>
              </div>

              {executing && (
                <Progress value={progress} className="mt-2" />
              )}
              {result && (
                <p className="text-sm text-muted-foreground">{result}</p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
