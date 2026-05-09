#!/usr/bin/env bash
# Refresh the bundled code-knowledge-graph at web/public/codegraph/.
#
# Pipeline (LLM only at step 3, via AWS Bedrock):
#   1. graphify update — re-extract AST nodes/edges from current source tree
#   2. cp graphify-out/* web/public/codegraph/  — bundle into Next.js public/
#   3. python scripts/label_codegraph_communities.py — Bedrock Sonnet labels
#      each community in Korean and writes graph.json.community_labels +
#      sidecar community_labels.json
#   4. inline patch graph.html + graph.json node.community_name fields with
#      the semantic labels (graphify embeds names at viz-build time, so we
#      have to patch in place for the HTML viewer to pick them up)
#
# Re-run after non-trivial code changes; the result must be committed.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "[1/4] graphify update . --force"
graphify update . --force

echo "[2/4] copying graphify-out → web/public/codegraph/"
cp graphify-out/graph.html graphify-out/graph.json graphify-out/manifest.json \
   graphify-out/GRAPH_REPORT.md web/public/codegraph/

echo "[3/4] enriching communities via Bedrock Sonnet (~3 min: label + description + key_concepts + top_files)"
python3 scripts/label_codegraph_communities.py

echo "[4/4] patching graph.html + graph.json with semantic community names"
python3 - <<'PY'
import json
labels = json.load(open('web/public/codegraph/community_labels.json'))
html = open('web/public/codegraph/graph.html').read()
patched = 0
for cid, label in labels.items():
    pattern = f'"community_name": "Community {cid}"'
    replacement = '"community_name": "' + label.replace('"', '\\"') + '"'
    n = html.count(pattern)
    if n:
        html = html.replace(pattern, replacement)
        patched += n
gj = json.load(open('web/public/codegraph/graph.json'))
for n in gj.get('nodes', []):
    cid = str(n.get('community', ''))
    if cid in labels:
        n['community_name'] = labels[cid]
open('web/public/codegraph/graph.html', 'w').write(html)
open('web/public/codegraph/graph.json', 'w').write(
    json.dumps(gj, ensure_ascii=False, indent=2))
print(f'  patched {patched} community_name occurrences in graph.html')
PY

echo "Done. Review web/public/codegraph/community_labels.json, then:"
echo "    git add web/public/codegraph/ && git commit -m 'chore(codegraph): refresh'"
echo "    docker build/push/deploy web image"
