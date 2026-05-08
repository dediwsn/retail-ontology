"""Annotate graphify-out/graph.json communities with Korean semantic labels.

Inspired by the labelled `community_labels` block in mfg-ontology's
graph.json (which graphify normally writes via its `extract --backend X`
LLM pipeline). We get the same effect by calling AWS Bedrock Sonnet
ourselves, so the retail repo doesn't need an external API key — the
EC2 IAM role already has Bedrock access.

Usage:
    python3 scripts/label_codegraph_communities.py \\
        --graph web/public/codegraph/graph.json \\
        [--limit 200] [--dry-run]

Idempotent — re-running re-labels (Bedrock is non-deterministic at
temperature 0.2 but the labels stay close to the same surface form).
Writes back to the same `graph.json` adding/replacing the top-level
`community_labels: {community_id: "한국어 라벨"}` key, plus a sidecar
`community_labels.json` mirror for clients that want a separate file.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

import boto3

REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
MODEL_ID = os.environ.get("BEDROCK_CHAT_MODEL_ID", "global.anthropic.claude-sonnet-4-6")

# Per-community node payload sent to the LLM. Cap to keep prompts small.
NODES_PER_COMMUNITY_FOR_PROMPT = 12


def _representative_nodes(nodes: List[Dict[str, Any]],
                           edges: List[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
    """For each community, pick up to N representative nodes ordered by
    in-degree + out-degree (a cheap proxy for "central" in that cluster).
    Returns {community_id: [node_dict, ...]}.
    """
    degree: Counter = Counter()
    for e in edges:
        s = e.get("source")
        t = e.get("target")
        if s: degree[s] += 1
        if t: degree[t] += 1

    by_com: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for n in nodes:
        cid = n.get("community")
        if cid is None:
            continue
        by_com[cid].append(n)

    # Sort each bucket by degree desc, take top-N.
    out: Dict[int, List[Dict[str, Any]]] = {}
    for cid, ns in by_com.items():
        ns.sort(key=lambda n: degree.get(n.get("id", ""), 0), reverse=True)
        out[cid] = ns[:NODES_PER_COMMUNITY_FOR_PROMPT]
    return out


def _format_for_prompt(reps: List[Dict[str, Any]]) -> str:
    """One-line per node: `path/to/file.py · LabelOrName · L42` style.
    Same shape graphify uses internally so the LLM sees familiar structure.
    """
    lines = []
    for n in reps:
        src = n.get("source_file") or ""
        loc = n.get("source_location") or ""
        label = n.get("label") or n.get("norm_label") or n.get("id") or "?"
        lines.append(f"  - {src}{(' ' + loc) if loc else ''} :: {label}")
    return "\n".join(lines)


def _label_one_community(client, cid: int, reps: List[Dict[str, Any]]) -> str:
    """Ask Sonnet for a 5–15-character Korean label that summarises
    the cluster's purpose. Returns plain string (no JSON wrapping).
    """
    snippet = _format_for_prompt(reps)
    prompt = (
        "다음은 한 코드베이스 내에서 자동 군집화로 묶인 한 *커뮤니티*의 대표 노드들입니다. "
        "이 커뮤니티가 무엇에 관한 것인지 *한국어 5~15자 이내의 라벨*로 요약해 주세요. "
        "불필요한 설명·따옴표·접두사 없이 라벨 텍스트만 단독으로 반환합니다.\n\n"
        f"커뮤니티 #{cid} 대표 노드 (degree 내림차순):\n{snippet}\n\n"
        "라벨:"
    )
    resp = client.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 60, "temperature": 0.2},
    )
    raw = resp["output"]["message"]["content"][0]["text"].strip()
    # Strip stray quotes / trailing punctuation the model sometimes adds.
    raw = raw.strip("\"'`「」 .,。")
    # Cap to 30 chars defensively (instruction said ≤15 but Sonnet wanders).
    return raw[:30] if raw else f"커뮤니티 {cid}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", default="web/public/codegraph/graph.json")
    ap.add_argument("--sidecar", default=None,
                    help="optional path for the community_labels.json mirror "
                         "(default: <graph dir>/community_labels.json)")
    ap.add_argument("--limit", type=int, default=999,
                    help="cap labelling to top-N largest communities; rest get "
                         "auto-labels '커뮤니티 N' as graceful fallback")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    graph_path = Path(args.graph)
    sidecar_path = Path(args.sidecar) if args.sidecar \
        else graph_path.parent / "community_labels.json"

    g = json.loads(graph_path.read_text(encoding="utf-8"))
    nodes = g.get("nodes") or []
    # graphify schema uses "links" (D3) but accept "edges" too.
    edges = g.get("links") or g.get("edges") or []
    if not nodes:
        print("error: graph.json has no nodes", file=sys.stderr)
        sys.exit(1)

    reps = _representative_nodes(nodes, edges)
    # Order communities by size (largest first) — labelling them earlier
    # so a partial run still produces useful coverage.
    communities = sorted(reps.items(), key=lambda kv: len(kv[1]), reverse=True)
    print(f"Found {len(communities)} communities; "
          f"largest has {len(communities[0][1])} representative nodes.")

    if args.dry_run:
        for cid, rs in communities[:5]:
            print(f"\n#{cid} ({len(rs)} reps):")
            print(_format_for_prompt(rs))
        return

    client = boto3.client("bedrock-runtime", region_name=REGION)
    labels: Dict[str, str] = {}
    for i, (cid, rs) in enumerate(communities):
        if i >= args.limit:
            labels[str(cid)] = f"커뮤니티 {cid}"
            continue
        try:
            label = _label_one_community(client, cid, rs)
        except Exception as e:
            print(f"  ! community {cid}: {e}", file=sys.stderr)
            label = f"커뮤니티 {cid}"
        labels[str(cid)] = label
        if (i + 1) % 10 == 0 or i < 5:
            print(f"  [{i+1}/{len(communities)}] #{cid} → {label}")

    g["community_labels"] = labels
    graph_path.write_text(json.dumps(g, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    sidecar_path.write_text(json.dumps(labels, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    print(f"\nWrote {len(labels)} community labels to:")
    print(f"  - {graph_path}  (graph.community_labels)")
    print(f"  - {sidecar_path}  (sidecar mirror)")


if __name__ == "__main__":
    main()
