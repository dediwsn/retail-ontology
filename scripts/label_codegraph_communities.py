"""Annotate graphify-out/graph.json communities with semantic Korean
metadata via AWS Bedrock Sonnet 4.6.

Replaces the simple `community_labels` map with a richer
`community_meta` schema:

    {
      "0": {
        "label": "API 클라이언트 타입 정의",                   <- 5–15자
        "description": "프론트엔드 fetch helpers + Pydantic 미러 타입.",  <- 1줄, ≤80자
        "top_files": ["web/lib/api-client.ts", ...],          <- 5개
        "key_concepts": ["TypeScript", "fetch", "타입 미러"],  <- 3개
        "node_count": 85
      },
      ...
    }

Two output files:
  - graph.community_labels  (legacy, just {cid: label}) — for backward compat
  - graph.community_meta    (new, full metadata)
  - sidecars: community_labels.json + community_meta.json

The page reads community_meta.json. graph.html keeps using the simple
labels via the in-place `community_name` patch (separate step, see
`scripts/refresh_codegraph.sh`).

Usage:
    python3 scripts/label_codegraph_communities.py \\
        --graph web/public/codegraph/graph.json [--limit 200] [--dry-run]

Re-running re-derives metadata. Bedrock at temperature 0.2 keeps labels
stable across runs (drift ≤ small word-order changes).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

import boto3

REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
MODEL_ID = os.environ.get("BEDROCK_CHAT_MODEL_ID", "global.anthropic.claude-sonnet-4-6")

NODES_PER_COMMUNITY_FOR_PROMPT = 15


def _representative_nodes(nodes: List[Dict[str, Any]],
                           edges: List[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
    degree: Counter = Counter()
    for e in edges:
        if e.get("source"): degree[e["source"]] += 1
        if e.get("target"): degree[e["target"]] += 1

    by_com: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for n in nodes:
        cid = n.get("community")
        if cid is None:
            continue
        by_com[cid].append(n)

    out: Dict[int, List[Dict[str, Any]]] = {}
    for cid, ns in by_com.items():
        ns.sort(key=lambda n: degree.get(n.get("id", ""), 0), reverse=True)
        out[cid] = ns[:NODES_PER_COMMUNITY_FOR_PROMPT]
    return out


def _format_for_prompt(reps: List[Dict[str, Any]]) -> str:
    lines = []
    for n in reps:
        src = n.get("source_file") or ""
        loc = n.get("source_location") or ""
        label = n.get("label") or n.get("norm_label") or n.get("id") or "?"
        lines.append(f"  - {src}{(' ' + loc) if loc else ''} :: {label}")
    return "\n".join(lines)


_JSON_BLOCK = re.compile(r"\{[\s\S]*\}", re.MULTILINE)


def _enrich_one(client, cid: int, reps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Single Bedrock call → JSON with label + description + concepts."""
    snippet = _format_for_prompt(reps)
    prompt = (
        "코드베이스 자동 군집화로 묶인 한 *커뮤니티*의 대표 노드 목록입니다. "
        "이 클러스터의 목적을 분석해 다음 JSON 형식으로 응답하세요. "
        "JSON 외 다른 텍스트(설명, 코드 펜스)는 절대 포함하지 마세요.\n\n"
        '{\n'
        '  "label": "5~15자 한국어 라벨 (제목 형태)",\n'
        '  "description": "이 클러스터가 무엇을 하는지 1줄 요약 (≤80자)",\n'
        '  "key_concepts": ["핵심 개념 1", "핵심 개념 2", "핵심 개념 3"]\n'
        '}\n\n'
        f"커뮤니티 #{cid} 대표 노드 (degree 내림차순, top {len(reps)}):\n"
        f"{snippet}\n\n"
        "JSON 응답:"
    )
    resp = client.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 400, "temperature": 0.2},
    )
    raw = resp["output"]["message"]["content"][0]["text"].strip()
    # Strip optional ```json ... ``` fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE).rstrip("`").strip()
    # Extract first {...} block (Sonnet sometimes adds a trailing newline)
    m = _JSON_BLOCK.search(raw)
    if not m:
        raise ValueError(f"no JSON found in response: {raw[:200]}")
    parsed = json.loads(m.group(0))
    label = str(parsed.get("label") or "").strip()[:30] or f"커뮤니티 {cid}"
    desc = str(parsed.get("description") or "").strip()[:120]
    concepts_raw = parsed.get("key_concepts") or []
    if not isinstance(concepts_raw, list):
        concepts_raw = [str(concepts_raw)]
    concepts = [str(c).strip()[:30] for c in concepts_raw[:3] if c]
    return {"label": label, "description": desc, "key_concepts": concepts}


def _top_files(reps: List[Dict[str, Any]], n: int = 5) -> List[str]:
    """Return up to n distinct source_file paths from the representative
    nodes. Order preserved (= degree order)."""
    seen: set = set()
    out: List[str] = []
    for node in reps:
        sf = (node.get("source_file") or "").strip()
        if not sf or sf in seen:
            continue
        seen.add(sf)
        out.append(sf)
        if len(out) >= n:
            break
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", default="web/public/codegraph/graph.json")
    ap.add_argument("--meta-out", default=None,
                    help="path for community_meta.json (default <graph dir>/community_meta.json)")
    ap.add_argument("--labels-out", default=None,
                    help="path for community_labels.json (default <graph dir>/community_labels.json)")
    ap.add_argument("--limit", type=int, default=999,
                    help="cap LLM calls; remaining communities get an auto-label '커뮤니티 N'")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    graph_path = Path(args.graph)
    meta_path = Path(args.meta_out) if args.meta_out \
        else graph_path.parent / "community_meta.json"
    labels_path = Path(args.labels_out) if args.labels_out \
        else graph_path.parent / "community_labels.json"

    g = json.loads(graph_path.read_text(encoding="utf-8"))
    nodes = g.get("nodes") or []
    edges = g.get("links") or g.get("edges") or []
    if not nodes:
        print("error: graph.json has no nodes", file=sys.stderr)
        sys.exit(1)

    reps = _representative_nodes(nodes, edges)
    sized = [(cid, len(by_com), by_com) for cid, by_com_list in reps.items()
             for by_com in [by_com_list]]
    # community sizes from the *full* node list (reps cap at 15, sizes can be larger)
    full_sizes: Counter = Counter()
    for n in nodes:
        cid = n.get("community")
        if cid is not None:
            full_sizes[cid] += 1
    communities = sorted(reps.keys(), key=lambda c: full_sizes[c], reverse=True)

    print(f"Found {len(communities)} communities; "
          f"largest = {full_sizes[communities[0]]} nodes.")

    if args.dry_run:
        for cid in communities[:3]:
            print(f"\n#{cid} ({full_sizes[cid]} nodes, top-files: "
                  f"{_top_files(reps[cid])}):")
            print(_format_for_prompt(reps[cid]))
        return

    client = boto3.client("bedrock-runtime", region_name=REGION)
    meta: Dict[str, Dict[str, Any]] = {}
    labels: Dict[str, str] = {}
    for i, cid in enumerate(communities):
        rs = reps[cid]
        size = full_sizes[cid]
        if i >= args.limit:
            entry = {
                "label": f"커뮤니티 {cid}",
                "description": "",
                "key_concepts": [],
                "top_files": _top_files(rs),
                "node_count": size,
            }
        else:
            try:
                enriched = _enrich_one(client, cid, rs)
            except Exception as e:
                print(f"  ! community {cid}: {e}", file=sys.stderr)
                enriched = {"label": f"커뮤니티 {cid}", "description": "",
                            "key_concepts": []}
            entry = {
                **enriched,
                "top_files": _top_files(rs),
                "node_count": size,
            }
        meta[str(cid)] = entry
        labels[str(cid)] = entry["label"]
        if (i + 1) % 10 == 0 or i < 5:
            preview = entry["description"][:50]
            print(f"  [{i+1}/{len(communities)}] #{cid} ({size}n) "
                  f"→ {entry['label']!r}  {preview!r}")

    g["community_labels"] = labels
    g["community_meta"] = meta

    graph_path.write_text(json.dumps(g, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    labels_path.write_text(json.dumps(labels, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"\nWrote enriched metadata for {len(meta)} communities:")
    print(f"  - {graph_path}  (graph.community_labels + community_meta)")
    print(f"  - {meta_path}   (rich metadata sidecar)")
    print(f"  - {labels_path} (legacy label-only sidecar)")


if __name__ == "__main__":
    main()
