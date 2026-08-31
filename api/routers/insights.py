"""
Scenario C — POST /api/insights (+ /api/insights/stream SSE variant).

Bedrock Sonnet 4.6 reads aggregated Neptune trend / ingredient / category
counts and produces a Korean MD-style insight + a chart_spec the frontend
renders inline. The streaming variant emits per-phase events:
  phase  → neptune aggregation
  phase  → bedrock summary
  delta  → token chunks from the LLM
  result → final {answer_ko, chart_spec, drill_down_subgraph}
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Generator, List

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.aws_clients import bedrock_runtime
from api.config import get_settings
from api.services import guardrails, neptune

logger = logging.getLogger(__name__)
router = APIRouter(tags=["insights"])


class InsightsRequest(BaseModel):
    q: str = Field(min_length=1, max_length=500)
    period_days: int = Field(default=28, ge=1, le=180)


class InsightsResponse(BaseModel):
    answer_ko: str
    chart_spec: Dict[str, Any]
    drill_down_subgraph: Dict[str, Any]


# ─── Aggregation queries ──────────────────────────────────────────────────


def _aggregate_trends() -> List[Dict[str, Any]]:
    """Trend ↔ Ingredient rollup. Each Trend node has a list of involved
    ingredients; we return up to 10 trends ranked by ingredient fanout."""
    cypher = """
        MATCH (t:Trend)-[:INVOLVES]->(i:Ingredient)
        WITH t, collect(DISTINCT i.name_ko) AS ingredients,
             count(DISTINCT i) AS fanout
        RETURN t.name_ko AS trend, t.type AS type,
               t.description_ko AS description,
               ingredients[..5] AS top_ingredients,
               fanout
        ORDER BY fanout DESC LIMIT 10
    """
    try:
        return neptune.open_cypher(cypher)
    except Exception as exc:  # noqa: BLE001
        logger.warning("trend aggregation failed: %s", str(exc)[:200])
        return []


SYSTEM_PROMPT = (
    "당신은 한국 Retail/CPG MD 전문 분석가입니다. 주어진 Neptune 트렌드 집계 데이터를 "
    "근거로 사용자 질문에 한국어로 간결하게 답합니다. 답변 구조:\n"
    "1) 핵심 요약 1-2문장\n"
    "2) 상위 트렌드 3-5개를 bullet로 — 각 항목은 '트렌드명 — 핵심 성분 / 인사이트'\n"
    "3) 시즌·페르소나 시사점 1-2문장\n"
    "수치는 항상 데이터에서 인용하고, 데이터에 없는 수치는 만들어내지 마세요."
)


def _bedrock_summarize(question: str, period_days: int, trends: List[Dict[str, Any]]) -> Generator[str, None, None]:
    """Stream MD-style insight text token-by-token via Bedrock Converse Stream.

    Yields raw text deltas. Caller wraps them into SSE delta events.
    Falls back to a deterministic recap if Bedrock is unavailable so the
    chart still has accompanying narrative."""
    s = get_settings()
    payload_lines = [
        f"질문: {question}",
        f"기간: 최근 {period_days}일",
        f"Neptune 집계 결과 (트렌드 {len(trends)}개):",
    ]
    for t in trends:
        ings = ", ".join(t.get("top_ingredients") or []) or "—"
        payload_lines.append(
            f"- {t.get('trend')} ({t.get('type')}, fanout={t.get('fanout')}): "
            f"성분=[{ings}] / {(t.get('description') or '')[:80]}"
        )
    user_msg = "\n".join(payload_lines)

    try:
        resp = bedrock_runtime().converse_stream(
            modelId=s.bedrock_chat_model_id,
            system=[{"text": SYSTEM_PROMPT}],
            messages=[{"role": "user", "content": [{"text": user_msg}]}],
            inferenceConfig={"maxTokens": 800, "temperature": 0.3},
        )
        for ev in resp.get("stream", []):
            if "contentBlockDelta" in ev:
                delta = ev["contentBlockDelta"].get("delta", {})
                txt = delta.get("text")
                if txt:
                    yield txt
    except Exception as exc:  # noqa: BLE001
        logger.warning("bedrock insights summarize failed: %s", str(exc)[:200])
        # Deterministic fallback so the page still has narrative.
        yield f"'{question}' 관련 상위 트렌드 {len(trends)}개를 정리했습니다.\n"
        for t in trends[:5]:
            ings = ", ".join((t.get("top_ingredients") or [])[:3])
            yield f"- {t.get('trend')} (관련 성분 {t.get('fanout')}개: {ings})\n"


def _guard_output(text: str) -> str:
    """Apply the OUTPUT guardrail to the assembled answer.

    Matches the pattern in services/agent.py: text deltas stream unscrubbed and
    the terminal event carries the authoritative, guardrailed text. That is a
    deliberate streaming trade-off, not an oversight — buffering the whole
    answer to scrub it first would remove the token-by-token effect the
    scenario exists to show.

    Never raises: insights degrades to the raw answer rather than 500-ing, the
    same way it falls back when Bedrock or Neptune is unavailable."""
    if not text:
        return text
    try:
        safe, intervened = guardrails.apply(text, source="OUTPUT")
        if intervened:
            logger.info("insights output guardrail intervened")
        return safe
    except Exception as exc:  # noqa: BLE001
        logger.warning("insights output guardrail failed (non-fatal): %s", str(exc)[:200])
        return text


def _chart_spec_from(trends: List[Dict[str, Any]], q: str, period_days: int) -> Dict[str, Any]:
    return {
        "type": "bar",
        "title": f"{q} — 지난 {period_days}일 트렌드 fanout",
        "data": [
            {"label": t.get("trend") or "", "value": int(t.get("fanout") or 0)}
            for t in trends
        ],
    }


# ─── Endpoints ────────────────────────────────────────────────────────────


@router.post("/insights", response_model=InsightsResponse)
def insights_endpoint(req: InsightsRequest) -> InsightsResponse:
    """Non-streaming: full Bedrock answer materialised then returned."""
    trends = _aggregate_trends()
    answer = _guard_output("".join(_bedrock_summarize(req.q, req.period_days, trends)))
    return InsightsResponse(
        answer_ko=answer or f"'{req.q}'에 대한 트렌드 데이터가 부족합니다.",
        chart_spec=_chart_spec_from(trends, req.q, req.period_days),
        drill_down_subgraph={"nodes": [], "edges": []},
    )


def _sse(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/insights/stream")
def insights_stream(req: InsightsRequest) -> StreamingResponse:
    """SSE: phase(neptune) → phase(bedrock) → delta tokens → result event.

    A `guardrail` event precedes `result` when the OUTPUT guardrail changed the
    assembled answer."""
    def stream():
        yield _sse("phase", {"name": "neptune", "detail": "Trend ↔ Ingredient 집계"})
        trends = _aggregate_trends()
        yield _sse("phase", {"name": "bedrock", "detail": f"Sonnet 4.6 분석 ({len(trends)}개 트렌드)"})

        full_answer = ""
        for chunk in _bedrock_summarize(req.q, req.period_days, trends):
            full_answer += chunk
            yield _sse("delta", {"text": chunk})

        safe_answer = _guard_output(full_answer)
        if safe_answer != full_answer:
            yield _sse("guardrail", {"action": "output_scrub"})
        yield _sse("result", {
            "answer_ko": safe_answer or f"'{req.q}'에 대한 트렌드 데이터가 부족합니다.",
            "chart_spec": _chart_spec_from(trends, req.q, req.period_days),
            "drill_down_subgraph": {"nodes": [], "edges": []},
        })

    return StreamingResponse(stream(), media_type="text/event-stream")
