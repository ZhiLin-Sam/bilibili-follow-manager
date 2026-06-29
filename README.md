# Bili Follow Manager

Bilibili 关注列表分析清理工具 — 扫码登录拉取全部关注，智能规则引擎识别营销号/人机号/僵尸号，批量取关。

## 功能

| 模块 | 说明 |
|------|------|
| 📡 拉取 | 扫码登录，拉取全部关注 (最多 5000) + 特别关注保护 |
| 🔍 过滤 | 11 条 KEEP + 10 条 DELETE 规则自动分类，深度探测 (投稿数/粉丝比/封禁/活跃度) |
| 🔎 审查 | 数据表搜索/排序/筛选，逐条标记保留或删除，特关和认证账号自动保护 |
| 🗑 取关 | 三级确认 (数量复核→名单复核→输入 DELETE)，批量执行取关 |

## 界面

支持双前端：
- **Tkinter GUI** — `python -m bili_manager`
- **Web (React + shadcn/ui)** — FastAPI 后端 + pywebview 桌面壳或浏览器访问

## 安装

```bash
git clone https://github.com/ZhiLin-Sam/bilibili-follow-manager.git
cd bilibili-follow-manager
pip install -e .
cd frontend && npm install && cd ..
```

## 使用

### Web 前端 (推荐)

```bash
# 终端1: FastAPI 后端
python -m uvicorn bili_manager.api_http:app --host 127.0.0.1 --port 9000

# 终端2: Vite 开发服务器
cd frontend && npm run dev
```
浏览器打开 `http://localhost:5173`

### Tkinter 桌面

```bash
python -m bili_manager
```

### pywebview 桌面壳

```bash
python -m bili_manager.app_webview
```

## 规则引擎

基于 TOML 配置文件 (`config/default_rules.toml`)，支持自定义添加：

- **KEEP 规则** (11 条)：知名认证、VIP 活跃、英文名有签名、品牌号、小说加认证等
- **DELETE 规则** (10 条)：已注销、bili_ 空号、免费领取、引流链接、短剧营销、金融营销等
- **深度探测**：封禁号 (spacesta=-2)、纯空号 (0投稿)、刷粉号 (关注/粉丝比 ≥5)、死号

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 (Web) | Vite + React 19 + TypeScript + Tailwind CSS v4 + shadcn/ui |
| 前端 (Desktop) | Tkinter (Python 标准库) |
| 后端 API | FastAPI + Uvicorn |
| 桌面壳 | pywebview |
| 数据 | SQLite |
| 规则 | TOML 配置 + 自定义 regex |
| 质量 | ruff + mypy (0 errors) |

## License

MIT
