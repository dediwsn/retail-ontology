#!/usr/bin/env python3
"""
Run the real API with every AWS boundary mocked — no account, no credentials.

    python3 scripts/devserver.py            # http://localhost:8000
    python3 scripts/devserver.py --port 8100

The FastAPI app, routers, Pydantic models, SSE vocabulary and auth middleware
all run for real; only the calls that would leave the process are faked. See
`mocks/aws.py` for exactly where the seam sits, and
docs/runbooks/local-mock-mode.md for the page-by-page walkthrough.

Env defaults mirror tests/conftest.py — `api.config.Settings` declares most
fields without defaults on purpose, so something has to supply them.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_DEFAULTS = {
    "AWS_REGION": "ap-northeast-2", "AWS_ACCOUNT_ID": "000000000000",
    "AWS_ACCESS_KEY_ID": "MOCK", "AWS_SECRET_ACCESS_KEY": "MOCK",
    "AURORA_SECRET_ARN": "arn:aws:secretsmanager:ap-northeast-2:000000000000:secret:mock",
    "AURORA_DATABASE_NAME": "ontology_mock",
    "NEPTUNE_ENDPOINT": "mock-neptune.local", "NEPTUNE_PORT": "8182",
    "OPENSEARCH_ENDPOINT": "https://mock.aoss.local", "OPENSEARCH_INDEX": "mock-index",
    "BEDROCK_KB_ID": "MOCKKB0001",
    "BEDROCK_GUARDRAIL_ID": "mock-guardrail", "BEDROCK_GUARDRAIL_VERSION": "1",
    "BEDROCK_RERANKER_INFERENCE_PROFILE_ARN": "arn:aws:bedrock:ap-northeast-2::mock/rerank",
    "AGENTCORE_MEMORY_ID": "mock_memory",
    "RAW_DOCS_BUCKET": "mock-raw-docs", "UPLOADS_BUCKET": "mock-uploads",
    "SYNTHETIC_DATA_BUCKET": "mock-synthetic-data",
    "ONTOLOGY_PROJECT": "ontology-retail", "ONTOLOGY_ENV": "mock",
    "COGNITO_USER_POOL_ID": "ap-northeast-2_mock",
    "COGNITO_USER_POOL_CLIENT_ID": "mockclientid",
    "PUBLIC_DOMAIN": "localhost:8000",
    # Auth off: there is no Cognito to redirect to, and the point is to walk
    # the pages. Matches tests/conftest.py, never a deployed configuration.
    "DEMO_PUBLIC_MODE": "true", "REQUIRE_ORIGIN_AUTH": "false",
    "CORS_ALLOW_ORIGINS": "http://localhost:3000,http://127.0.0.1:3000",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--reload", action="store_true")
    args = ap.parse_args()

    for k, v in _DEFAULTS.items():
        os.environ.setdefault(k, v)

    from mocks import aws as mock_aws
    import api.main  # noqa: F401  — imports settings + routers under the defaults
    mock_aws.install()

    import uvicorn
    print(f"\n  mock API  →  http://{args.host}:{args.port}")
    print(f"  docs      →  http://{args.host}:{args.port}/docs")
    print("  AWS calls →  none (mocks/aws.py)\n")
    uvicorn.run("api.main:app", host=args.host, port=args.port, reload=args.reload,
                log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
