"""LangGraph → SSE 流式桥接

使用 Queue + Thread 方案，避免 Flask 同步/异步冲突。
"""

import json
import logging
import queue
import threading
import time
from typing import Generator

from .screener_state import ScreenerState
from .screener_graph import build_graph
from .single_stock_state import SingleStockState
from .single_stock_graph import build_single_stock_graph

logger = logging.getLogger(__name__)

# SSE 超时 (秒)
DEFAULT_TIMEOUT = 300
# 心跳间隔 (秒)
HEARTBEAT_INTERVAL = 15


def run_graph_with_queue(initial_state: dict) -> queue.Queue:
    """在后台线程运行 graph.invoke()，通过 Queue 推送每步结果。

    Returns:
        queue.Queue: 消费方通过 sse_generator() 读取 SSE 事件。
    """
    q: queue.Queue = queue.Queue()

    def _run() -> None:
        graph = build_graph().compile()
        try:
            # 同步执行，graph.stream() 返回每个节点的输出
            for chunk in graph.stream(initial_state, stream_mode="updates"):
                # chunk 格式: {"node_name": {state_update}}
                for node_name, delta in chunk.items():
                    # 提取关键字段，避免推送整个 state
                    payload = {"node": node_name}

                    if node_name == "macro":
                        payload["sectors"] = delta.get("sectors", [])
                        payload["macro_reasoning"] = delta.get("macro_reasoning", "")
                    elif node_name == "lookup":
                        payload["top_count"] = len(delta.get("top_picks", []))
                        payload["top_picks"] = delta.get("top_picks", [])
                        payload["summary"] = delta.get("summary", "")
                        payload["candidate_count"] = len(delta.get("candidate_stocks", []))

                    # 也检查 error
                    if delta.get("error"):
                        payload["error"] = delta["error"]

                    q.put(("node_done", payload))

            q.put(("end", None))

        except Exception as e:
            logger.error(f"Graph 执行失败: {e}")
            q.put(("error", str(e)))

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return q


def sse_generator(
    event_queue: queue.Queue,
    timeout: int = DEFAULT_TIMEOUT,
) -> Generator[str, None, None]:
    """消费 Queue，生成 SSE (Server-Sent Events) 字符串。

    用法:
        return Response(
            stream_with_context(sse_generator(q)),
            mimetype="text/event-stream",
        )
    """
    start = time.time()
    last_heartbeat = start

    while True:
        elapsed = time.time() - start

        # 超时保护
        if elapsed > timeout:
            yield _sse("error", {"error": "分析超时"})
            yield _sse("end", {})
            return

        try:
            event_type, data = event_queue.get(timeout=1)
        except queue.Empty:
            # 发送心跳，防止代理/浏览器断开连接
            if time.time() - last_heartbeat >= HEARTBEAT_INTERVAL:
                yield ": heartbeat\n\n"
                last_heartbeat = time.time()
            continue

        last_heartbeat = time.time()

        if event_type == "end":
            yield _sse("end", {})
            return

        if event_type == "error":
            yield _sse("error", {"error": data})
            yield _sse("end", {})
            return

        # event_type == "node_done"
        yield _sse("node_done", data)

        # Step 3 评分中: 单独推每只股票卡片 (渐进式渲染)
        if data.get("node") == "score":
            scored = data.get("scored_stocks", [])
            if scored:
                # 已在 node_done 中推送摘要，卡片由前端自行渲染
                # 这里可选推 card 事件
                pass


def _sse(event: str, data: dict) -> str:
    """构建一条 SSE 消息。"""
    return f"event: {event}\ndata: {json.dumps(data, default=str, ensure_ascii=False)}\n\n"


def run_single_stock_with_queue(initial_state: dict) -> queue.Queue:
    """在后台线程运行个股分析 graph，通过 Queue 推送每步结果。"""
    q: queue.Queue = queue.Queue()

    def _run() -> None:
        graph = build_single_stock_graph().compile()
        try:
            for chunk in graph.stream(initial_state, stream_mode="updates"):
                for node_name, delta in chunk.items():
                    payload = {"node": node_name}
                    if node_name == "resolve":
                        payload["resolved_code"] = delta.get("resolved_code", "")
                        payload["resolved_name"] = delta.get("resolved_name", "")
                    elif node_name == "industry_context":
                        payload["csic_sector"] = delta.get("csic_sector", "")
                        payload["peers"] = delta.get("peers", [])
                        payload["concept_boards"] = delta.get("concept_boards", [])
                        payload["industry_context"] = delta.get("industry_context", "")
                        payload["web_news"] = delta.get("web_news", [])
                    elif node_name == "valuation":
                        payload["pe"] = delta.get("pe", 0)
                        payload["pb"] = delta.get("pb", 0)
                    elif node_name == "quality":
                        payload["roe"] = delta.get("roe", 0)
                        payload["gross_margin"] = delta.get("gross_margin", 0)
                    elif node_name == "growth":
                        payload["earnings_cagr_3y"] = delta.get("earnings_cagr_3y", 0)
                    elif node_name == "ai_thesis":
                        payload["total_score"] = delta.get("total_score", 0)
                        payload["score_breakdown"] = delta.get("score_breakdown", {})
                        payload["recommendation"] = delta.get("recommendation", "")
                        payload["ai_thesis"] = delta.get("ai_thesis", "")
                        # ── ValueClaw 巴菲特评分 ──
                        payload["buffett_score"] = delta.get("buffett_score", 0)
                        payload["buffett_breakdown"] = delta.get("buffett_breakdown", {})
                        payload["owner_earnings"] = delta.get("owner_earnings")
                        payload["fcf_yield"] = delta.get("fcf_yield")
                        payload["peg"] = delta.get("peg")

                    if delta.get("error"):
                        payload["error"] = delta["error"]

                    q.put(("node_done", payload))

            q.put(("end", None))
        except Exception as e:
            logger.error(f"Single stock graph failed: {e}")
            q.put(("error", str(e)))

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return q
