# Stock Screener — LangGraph Agent 重构方案

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 用 LangGraph 替代现有 Flask 后台线程 + 轮询架构，实现真正流式的 AI 选股 agent，前端通过 SSE 实时接收思维链与股票卡片。

**Architecture:**
- 后端：LangGraph `StateGraph` 建模 4 步 pipeline（宏观定调 → 成分股提取 → 量化评分 → 排序输出），每步通过 `astream_events` 推 SSE
- 前端：`EventSource` 接收 SSE，解析 `node_start/node_end/custom_event` 渲染思维链步骤 + 股票卡片
- UI：升级为专业投研终端风格，暗色主题 + 步骤时间线 + 卡片轮播

**Tech Stack:** Python 3.11+, LangGraph, langchain-deepseek, Flask + flask-sse (or custom SSE generator), vanilla HTML/CSS/JS (保持无框架)

---

## 架构对比

| 维度 | 现有架构 | LangGraph 架构 |
|------|---------|---------------|
| 流程控制 | 后台线程 + `time.sleep` + 手动状态 | `StateGraph` 自动编排，节点间按条件路由 |
| 实时性 | 前端 2s 轮询 `/api/status` | SSE 实时推送，节点完成即刻到达 |
| 思维链 | 无 | 每步 `node_start` 带推理文本 |
| Step 3 触发 | ❌ 从未自动调用 | ✅ graph 自动从 Step2→Step3 |
| 错误处理 | 手动 try/catch + 状态置 error | `add_conditional_edges` 错误回退 |
| 可调试性 | 看日志 grep | LangSmith / LangGraph Studio 可视化 |

---

## 流程图 (LangGraph StateGraph)

```
START
  │
  ▼
[Step1: macro_analysis]  ← DeepSeek 宏观分析
  │  emit: reasoning, sectors[]
  ▼
[Step2: fetch_stocks]    ← 成分股提取 (CSIC 缓存 / Baostock)
  │  emit: candidate_count, sector_stats
  ▼
[Step3: score_batch]     ← 逐只量化评分 (PE/ROE/PEG/MCAP)
  │  emit: stock_score, card data (流式，每只推一张卡片)
  ▼
[Step4: rank_output]     ← 排序 + Top N 汇总
  │  emit: final_cards[], summary
  ▼
END
```

---

## 状态定义 (TypedDict)

```python
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

class StockScreenerState(TypedDict):
    # 用户输入
    user_query: str                    # 用户原始查询
    user_id: int                       # 当前用户 ID
    
    # Step 1 产出
    macro_reasoning: str               # DeepSeek 宏观分析原文
    sectors: list[str]                 # 推荐板块列表
    
    # Step 2 产出
    candidate_stocks: list[str]        # 候选股票代码列表
    stock_infos: dict[str, dict]       # {code: {name, sector, ...}}
    
    # Step 3 产出 (渐进式)
    scored_stocks: list[dict]          # 评分后的股票，逐步追加
    batch_progress: dict               # {total, current}
    
    # Step 4 产出
    top_picks: list[dict]              # Top N 精选
    summary: str                       # 最终汇总文本
    
    # 控制
    error: str | None                  # 错误信息
    current_step: int                  # 当前步骤 1-4
```

---

## 任务拆分

### Task 1: 安装 LangGraph 依赖 + 验证

**Objective:** 在服务器和本地安装 langgraph 及相关依赖

**Files:**
- Modify: `requirements.txt`

**Steps:**

1. 添加依赖到 `requirements.txt`:
```
langgraph>=0.2.0
langchain-deepseek>=0.1.0
```

2. 在服务器执行:
```bash
source /opt/stock-screener-app/venv/bin/activate
pip install langgraph langchain-deepseek
```

3. 验证导入:
```bash
python -c "from langgraph.graph import StateGraph, END; print('OK')"
```

---

### Task 2: 创建 StateGraph 骨架 (`core/screener_graph.py`)

**Objective:** 建立 4 节点的空骨架图，验证编译与基础运行

**Files:**
- Create: `core/screener_graph.py`
- Create: `core/screener_state.py`

**Steps:**

1. 创建 `core/screener_state.py`:
```python
from typing import TypedDict

class ScreenerState(TypedDict):
    user_query: str
    user_id: int
    macro_reasoning: str
    sectors: list[str]
    candidate_stocks: list[str]
    stock_infos: dict
    scored_stocks: list[dict]
    batch_progress: dict
    top_picks: list[dict]
    summary: str
    error: str | None
    current_step: int
```

2. 创建 `core/screener_graph.py`:
```python
from langgraph.graph import StateGraph, END
from .screener_state import ScreenerState

def node_macro(state: ScreenerState) -> ScreenerState:
    state["current_step"] = 1
    return state

def node_fetch(state: ScreenerState) -> ScreenerState:
    state["current_step"] = 2
    return state

def node_score(state: ScreenerState) -> ScreenerState:
    state["current_step"] = 3
    return state

def node_rank(state: ScreenerState) -> ScreenerState:
    state["current_step"] = 4
    return state

def build_graph() -> StateGraph:
    builder = StateGraph(ScreenerState)
    builder.add_node("macro", node_macro)
    builder.add_node("fetch", node_fetch)
    builder.add_node("score", node_score)
    builder.add_node("rank", node_rank)
    builder.set_entry_point("macro")
    builder.add_edge("macro", "fetch")
    builder.add_edge("fetch", "score")
    builder.add_edge("score", "rank")
    builder.add_edge("rank", END)
    return builder
```

3. 验证编译:
```bash
cd /opt/stock-screener-app && source venv/bin/activate
python -c "from core.screener_graph import build_graph; g = build_graph().compile(); print(g.get_graph().draw_ascii())"
```

---

### Task 3: 实现 SSE 生成器 (`core/stream.py`)

**Objective:** 创建一个 LangGraph → SSE 事件流的 bridge

**Files:**
- Create: `core/stream.py`

**Steps:**

```python
import json
import asyncio
from typing import AsyncGenerator
from .screener_graph import build_graph
from .screener_state import ScreenerState

async def stream_analysis(user_id: int, user_query: str) -> AsyncGenerator[str, None]:
    """Run the graph and yield SSE events for each step."""
    graph = build_graph().compile()
    initial_state: ScreenerState = {
        "user_query": user_query,
        "user_id": user_id,
        "macro_reasoning": "",
        "sectors": [],
        "candidate_stocks": [],
        "stock_infos": {},
        "scored_stocks": [],
        "batch_progress": {},
        "top_picks": [],
        "summary": "",
        "error": None,
        "current_step": 0,
    }
    
    # Emit START event
    yield f"event: start\ndata: {json.dumps({'step': 0, 'message': '开始分析…'})}\n\n"
    
    try:
        # Use astream_events for node-level streaming
        async for event in graph.astream_events(initial_state, version="v2"):
            kind = event["event"]
            if kind == "on_chain_start" and "node" in event.get("name", ""):
                # Extra safety: only forward recognized nodes
                pass
            elif kind == "on_chain_end":
                node_name = event.get("name", "")
                output = event.get("data", {}).get("output", {})
                # Forward node completion with its output
                if node_name in ("macro", "fetch", "score", "rank"):
                    yield f"event: node_done\ndata: {json.dumps({'node': node_name, 'output': output}, default=str)}\n\n"
    except Exception as e:
        yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
    
    # Emit END event
    yield f"event: end\ndata: {json.dumps({})}\n\n"
```

> ⚠️ `astream_events` 在同步 Flask 里需要用 `asyncio.run()` 包装或改用 Flask[async]。后续 Task 处理。

---

### Task 4: 接入 DeepSeek 到 `node_macro`

**Objective:** 将现有 `analyze_macro_sectors_with_ai()` 逻辑拆入 `node_macro`

**Files:**
- Modify: `core/screener_graph.py` (node_macro)
- Reference: `core/sector_analyzer.py` (analyze_macro_sectors_with_ai)

**Steps:**

```python
def node_macro(state: ScreenerState) -> ScreenerState:
    from .sector_analyzer import analyze_macro_sectors_with_ai
    
    ai_analysis = analyze_macro_sectors_with_ai()
    
    state["macro_reasoning"] = ai_analysis.get("reasoning", "")
    state["sectors"] = ai_analysis.get("sectors", [])
    state["current_step"] = 1
    
    if not state["sectors"]:
        state["error"] = "AI 未能推导出有效板块"
    
    return state
```

---

### Task 5: 接入成分股提取到 `node_fetch`

**Objective:** 复用现有 `get_stocks_from_sectors()` 逻辑

**Files:**
- Modify: `core/screener_graph.py` (node_fetch)

```python
def node_fetch(state: ScreenerState) -> ScreenerState:
    from .ai_fallback import get_stocks_from_sectors
    
    # ai_result 需要从 step1 传给 step2 — 用 state 里的 sectors 重建
    ai_result = {"sectors_detail": {}}  # 实际需从 sector_analyzer 中提取
    stocks, infos = get_stocks_from_sectors(state["sectors"], ai_result)
    
    state["candidate_stocks"] = stocks
    state["stock_infos"] = infos
    state["current_step"] = 2
    
    if not stocks:
        state["error"] = "未找到成分股"
    
    return state
```

---

### Task 6: 接入量化评分到 `node_score` + `node_rank`

**Objective:** 流式评分 + 排序

```python
def node_score(state: ScreenerState) -> ScreenerState:
    from .stock_screener import pre_screen_stocks, deep_screen_stock
    from .scorer import calculate_score
    from .data_fetcher import get_index_data
    
    index_hist = get_index_data()
    scored = []
    
    for code in state["candidate_stocks"]:
        info = state["stock_infos"].get(code, {})
        passed, reason, yf_data = deep_screen_stock(code, index_hist=index_hist)
        score_report = calculate_score(code, info, yf_data) if yf_data else None
        
        scored.append({
            "code": code,
            "name": info.get("name", code),
            "passed": passed,
            "reason": reason,
            "score": score_report.get("total_score", 0) if score_report else 0,
            "pe": score_report.get("pe", 0) if score_report else 0,
            "roe": score_report.get("roe", 0) if score_report else 0,
            "report": score_report,
        })
    
    state["scored_stocks"] = scored
    state["current_step"] = 3
    return state


def node_rank(state: ScreenerState) -> ScreenerState:
    # Sort by score descending, passed first
    passed = [s for s in state["scored_stocks"] if s["passed"]]
    failed = [s for s in state["scored_stocks"] if not s["passed"]]
    passed.sort(key=lambda x: x["score"], reverse=True)
    
    state["top_picks"] = passed[:10]  # Top 10
    state["summary"] = f"从 {len(state['scored_stocks'])} 只候选股中筛选出 {len(passed)} 只达标，精选 Top {len(state['top_picks'])}"
    state["current_step"] = 4
    return state
```

---

### Task 7: 升级 Flask 路由 — SSE endpoint

**Objective:** 新增 `/api/analyze_stream` 端点，支持 SSE

**Files:**
- Modify: `app.py` (new route)

```python
from flask import Response, stream_with_context
import asyncio
import json

@app.route("/api/analyze_stream", methods=["GET"])
@login_required
def analyze_stream():
    user_query = request.args.get("q", "帮我找被低估的A股价值洼地")
    
    def generate():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            async_gen = stream_analysis(current_user.id, user_query)
            while True:
                try:
                    chunk = loop.run_until_complete(async_gen.__anext__())
                    yield chunk
                except StopAsyncIteration:
                    break
        finally:
            loop.close()
    
    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )
```

> ⚠️ Flask 同步模式下跑 asyncio 需要额外处理。备选方案：改用 `graph.invoke()` 同步调用 + 在每个 node 里用 `queue.Queue` 推事件，另一个生成器消费队列。

---

### Task 8: 修复同步/异步冲突 — 用 Queue 方案

**Objective:** 替代 Task 7 的 asyncio 方案，用线程安全 Queue 解耦

**Files:**
- Modify: `core/stream.py`
- Modify: `app.py`

**方案:**
```python
# core/stream.py
import queue
import threading

def run_graph_with_queue(initial_state: dict) -> queue.Queue:
    """Run graph in a thread, push events to a Queue."""
    q = queue.Queue()
    
    def _run():
        graph = build_graph().compile()
        try:
            # 同步 invoke，用 callback 推事件
            for event in graph.stream(initial_state):
                q.put(("node_done", event))
        except Exception as e:
            q.put(("error", str(e)))
        q.put(("end", None))
    
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return q


def sse_generator(q: queue.Queue, timeout: int = 300):
    """Consume queue and yield SSE chunks."""
    import time
    start = time.time()
    while True:
        try:
            event_type, data = q.get(timeout=1)
            if event_type == "end":
                yield "event: end\ndata: {}\n\n"
                return
            if event_type == "error":
                yield f"event: error\ndata: {json.dumps({'error': data})}\n\n"
                return
            yield f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"
        except queue.Empty:
            if time.time() - start > timeout:
                yield f"event: error\ndata: {json.dumps({'error': '分析超时'})}\n\n"
                return
            # Send heartbeat
            yield ": heartbeat\n\n"
```

**app.py 路由:**
```python
@app.route("/api/analyze", methods=["POST"])
@login_required
def analyze():
    data = request.json or {}
    user_query = data.get("q", "帮我找被低估的A股价值洼地")
    
    initial_state = {
        "user_query": user_query,
        "user_id": current_user.id,
        # ... 其他字段默认值
    }
    
    q = run_graph_with_queue(initial_state)
    
    return Response(
        stream_with_context(sse_generator(q)),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
```

---

### Task 9: 升级前端 — SSE EventSource 替换轮询

**Objective:** 用 `EventSource` 替代 `setInterval` 轮询

**Files:**
- Modify: `templates/ai_chat.html`

```javascript
function sendMessage() {
  const input = document.getElementById('userInput');
  const text = input.value.trim();
  if (!text) return;
  
  addMsg(text, 'user');
  input.value = '';
  setStatus(true);
  
  // Create SSE connection
  const es = new EventSource(`/api/analyze?q=${encodeURIComponent(text)}`);
  
  es.addEventListener('start', e => {
    const d = JSON.parse(e.data);
    addSystemLog(`[SYS] ${d.message}`);
  });
  
  es.addEventListener('node_done', e => {
    const d = JSON.parse(e.data);
    if (d.node === 'macro') {
      addSystemLog(`[PASS] 宏观分析完成 — ${d.output.sectors?.length || 0} 个板块`, 'pass');
      if (d.output.macro_reasoning) {
        addSummary({ reasoning: d.output.macro_reasoning, sectors: d.output.sectors });
      }
    } else if (d.node === 'fetch') {
      addSystemLog(`[PASS] 成分股提取完成 — ${d.output.candidate_stocks?.length || 0} 只`, 'pass');
    } else if (d.node === 'score') {
      addSystemLog(`[PASS] 评分完成 — ${d.output.scored_stocks?.length || 0} 只`, 'pass');
    } else if (d.node === 'rank') {
      addSystemLog(`[PASS] 精选 Top ${d.output.top_picks?.length || 0}`, 'pass');
      if (d.output.top_picks) addCards(d.output.top_picks);
      setStatus(false);
      es.close();
    }
  });
  
  es.addEventListener('error', e => {
    let msg = '未知错误';
    try { msg = JSON.parse(e.data).error; } catch(_) {}
    addSystemLog(`[FAIL] ${msg}`, 'fail');
    setStatus(false);
    es.close();
  });
  
  es.onerror = () => {
    addSystemLog('[FAIL] 连接中断', 'fail');
    setStatus(false);
    es.close();
  };
}
```

---

### Task 10: UI 升级 — 思维链时间线 + 投研终端风格

**Objective:** 将系统日志从纯文本升级为可视化的步骤时间线

**Files:**
- Modify: `templates/ai_chat.html` (CSS + HTML + JS)

**新增 CSS:**
```css
/* Step Timeline */
.step-timeline {
  position: relative;
  padding-left: 24px;
  margin: 8px 0;
}
.step-timeline::before {
  content: '';
  position: absolute;
  left: 8px;
  top: 0;
  bottom: 0;
  width: 2px;
  background: var(--border);
}
.step-item {
  position: relative;
  padding: 8px 12px;
  margin-bottom: 8px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  font-size: 13px;
}
.step-item::before {
  content: '';
  position: absolute;
  left: -20px;
  top: 14px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--border);
}
.step-item.active::before { background: var(--primary); animation: pulse 1.5s infinite; }
.step-item.done::before { background: var(--accent); }
.step-item.fail::before { background: var(--danger); }
.step-item .step-label {
  font-size: 11px;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.step-item .step-title { font-weight: 600; margin: 2px 0 4px; }
.step-item .step-detail { font-size: 12px; color: var(--muted); }
```

**新增 HTML 容器（放在 #chat 上方或内部）:**
```html
<div id="timeline" class="step-timeline" style="display:none"></div>
```

**JS 函数:**
```javascript
function addTimelineStep(id, label, title, detail = '', status = 'active') {
  const tl = document.getElementById('timeline');
  tl.style.display = 'block';
  
  let el = document.getElementById(`step-${id}`);
  if (!el) {
    el = document.createElement('div');
    el.id = `step-${id}`;
    el.className = 'step-item';
    tl.appendChild(el);
  }
  el.className = `step-item ${status}`;
  el.innerHTML = `
    <div class="step-label">${label}</div>
    <div class="step-title">${title}</div>
    ${detail ? `<div class="step-detail">${detail}</div>` : ''}
  `;
  scrollDown();
}
```

在 SSE `node_done` 回调里调用:
```javascript
if (d.node === 'macro') {
  addTimelineStep('macro', 'Step 1', '宏观分析', `${d.output.sectors?.length || 0} 个板块`, 'done');
} else if (d.node === 'fetch') {
  addTimelineStep('fetch', 'Step 2', '成分股提取', `${d.output.candidate_stocks?.length || 0} 只候选`, 'done');
}
```

---

### Task 11: 流式推送单只股票卡片（渐进式渲染）

**Objective:** Step 3 每评完一只股票就通过 SSE 推一张卡片到前端

**Files:**
- Modify: `core/screener_graph.py` (node_score — split into streaming)
- Modify: `core/stream.py` (custom event pushing)
- Modify: `templates/ai_chat.html` (card_received handler)

**方案:** 在 `node_score` 里每评完一只就 `q.put(("card", stock_data))`

前端:
```javascript
es.addEventListener('card', e => {
  addCards([JSON.parse(e.data)]);
});
```

---

### Task 12: 部署 + 端到端测试

**Objective:** 推代码到服务器，重启服务，全程跑通

**Steps:**
1. `git add -A && git commit && git push`
2. 服务器 pull + install deps + restart
3. 浏览器打开 /ai，输入查询，验证:
   - ✅ 思维链时间线实时展示
   - ✅ 股票卡片渐进式出现
   - ✅ Enter 键正常（保持已有修复）
   - ✅ 全程无 2s 轮询抖动
4. 查看 `journalctl -u stock-screener -f` 确认无异常

---

## 风险 & 取舍

| 风险 | 应对 |
|------|------|
| LangGraph + Flask 同步异步冲突 | 用 Queue + Thread 方案（Task 8），避免 asyncio |
| 流式评分耗时长（几百只股票） | 每只推送一张卡片，前端渐进渲染，不阻塞 |
| DeepSeek API 限速 | 复用现有限速逻辑，Step1 单次调用 |
| 现有用户 session 状态兼容 | graph 独立运行，不依赖 Flask-Login session 状态 |

---

## 文件变更清单

| 操作 | 文件 |
|------|------|
| Create | `core/screener_state.py` |
| Create | `core/screener_graph.py` |
| Create | `core/stream.py` |
| Modify | `app.py` (新增 `/api/analyze` SSE 路由) |
| Modify | `templates/ai_chat.html` (重写 JS + CSS + HTML) |
| Modify | `requirements.txt` (加 langgraph, langchain-deepseek) |
| Deprecate | `core/user_state.py` (graph 自带状态管理，旧轮询相关可逐步弃用) |
