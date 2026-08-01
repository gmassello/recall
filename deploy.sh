#!/usr/bin/env bash
set -euo pipefail

STACK=${STACK_NAME:-recall}
ROOT=$(cd "$(dirname "$0")" && pwd)
BACKEND=$ROOT/backend
BUILD=$BACKEND/build

command -v aws >/dev/null || { echo "aws CLI not found"; exit 1; }

if [ -f "$BACKEND/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$BACKEND/.env"
    set +a
fi
CLUSTER=${COCKROACH_CLUSTER:-${COCKROACH_MCP_CLUSTER_ID:-}}

if [ "${CREATE_CLUSTER:-}" = 1 ]; then
    command -v ccloud >/dev/null || { echo "ccloud CLI not found: https://www.cockroachlabs.com/docs/cockroachcloud/ccloud-get-started"; exit 1; }
    echo "==> Creating the CockroachDB Basic cluster '$STACK'"
    ccloud cluster create basic "$STACK" --cloud GCP --spend-limit 0
    echo "Now put its connection string in backend/.env as DATABASE_URL and rerun without CREATE_CLUSTER."
    exit 0
fi

if command -v ccloud >/dev/null && [ -n "$CLUSTER" ]; then
    echo "==> Checking the CockroachDB cluster with ccloud"
    LISTING=$(ccloud cluster list 2>&1) || {
        echo "$LISTING"
        echo "ccloud is not authenticated: run 'ccloud auth login' (it has no non-interactive mode)"
        exit 1
    }
    ROW=$(echo "$LISTING" | grep -F "$CLUSTER" || true)
    [ -n "$ROW" ] || { echo "cluster '$CLUSTER' is not in this organization"; exit 1; }
    echo "$ROW" | grep -q CLUSTER_STATE_CREATED || {
        echo "cluster '$CLUSTER' is not ready, deploying now would only fail at runtime:"
        echo "$ROW"
        exit 1
    }
    echo "    $CLUSTER is ready"
fi

: "${DATABASE_URL:?DATABASE_URL is missing: set it in backend/.env or in the environment}"

if [ "${LLM_PROVIDER:-}" = "anthropic" ] && ! grep -qi '^anthropic' "$BACKEND/requirements-lambda.txt"; then
    echo "LLM_PROVIDER=anthropic but the anthropic SDK is not in requirements-lambda.txt:"
    echo "the Lambda would fail on import. Add it there (see the recall-switch-llm-provider skill)."
    exit 1
fi

export AWS_DEFAULT_REGION=${AWS_REGION:-${AWS_DEFAULT_REGION:-$(aws configure get region || echo us-east-1)}}
REGION=$AWS_DEFAULT_REGION

aws sts get-caller-identity >/dev/null 2>&1 || {
    echo "AWS credentials are not valid: check AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY in backend/.env"
    echo "(temporary credentials also need AWS_SESSION_TOKEN, and they expire)"
    exit 1
}
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
STAGING="$STACK-artifacts-$ACCOUNT-$REGION"

echo "==> Building the Lambda package"
rm -rf "$BUILD"
mkdir -p "$BUILD"
python3 -m pip install -q -r "$BACKEND/requirements-lambda.txt" -t "$BUILD" \
    --platform manylinux2014_aarch64 --platform manylinux_2_28_aarch64 \
    --python-version 3.13 --only-binary=:all:
cp -r "$BACKEND/app" "$BACKEND/seed" "$BACKEND/certs" "$BACKEND/run.sh" "$BUILD/"
chmod +x "$BUILD/run.sh"
find "$BUILD" -name '__pycache__' -type d -prune -exec rm -rf {} +
echo "    package size: $(du -sh "$BUILD" | cut -f1)  (Lambda limit: 250 MB unzipped)"

echo "==> Deploying the stack"
STATUS=$(aws cloudformation describe-stacks --stack-name "$STACK" \
    --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo NONE)
if [ "$STATUS" = ROLLBACK_COMPLETE ] || [ "$STATUS" = REVIEW_IN_PROGRESS ]; then
    echo "    $STACK is in $STATUS (a first creation that failed): deleting it before retrying"
    aws cloudformation delete-stack --stack-name "$STACK"
    aws cloudformation wait stack-delete-complete --stack-name "$STACK"
fi
aws s3api head-bucket --bucket "$STAGING" 2>/dev/null || aws s3 mb "s3://$STAGING" --region "$REGION"
aws s3api put-bucket-lifecycle-configuration --bucket "$STAGING" --lifecycle-configuration '{
    "Rules": [{"ID": "expire-old-packages", "Status": "Enabled",
               "Filter": {}, "Expiration": {"Days": 30}}]}'
aws cloudformation package \
    --template-file "$BACKEND/template.yaml" \
    --s3-bucket "$STAGING" \
    --output-template-file "$BACKEND/.packaged.yaml" >/dev/null
PARAMS_FILE="$BUILD/.parameters.json"
python3 - "$PARAMS_FILE" <<'PYEOF'
import json, os, sys

env = os.environ.get
params = {
    "DatabaseUrl": os.environ["DATABASE_URL"],
    "CockroachMcpUrl": env("COCKROACH_MCP_URL", ""),
    "CockroachMcpApiKey": env("COCKROACH_MCP_API_KEY", ""),
    "CockroachMcpClusterId": env("COCKROACH_MCP_CLUSTER_ID", ""),
    "BedrockModelId": env("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"),
    "BedrockEmbeddingModelId": env("BEDROCK_EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0"),
    "LlmProvider": env("LLM_PROVIDER", "gemini"),
    "EmbeddingProvider": env("EMBEDDING_PROVIDER", "gemini"),
    "GeminiApiKey": env("GEMINI_API_KEY", ""),
    "GeminiModel": env("GEMINI_MODEL", "gemini-flash-latest"),
    "GeminiEmbeddingModel": env("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
    "DemoApiKey": env("DEMO_API_KEY", ""),
}
with open(sys.argv[1], "w") as fh:
    json.dump({"Parameters": params}, fh)
PYEOF
aws cloudformation deploy \
    --template-file "$BACKEND/.packaged.yaml" \
    --stack-name "$STACK" \
    --capabilities CAPABILITY_IAM \
    --no-fail-on-empty-changeset \
    --parameter-overrides "file://$PARAMS_FILE"
rm -f "$PARAMS_FILE"

out() {
    aws cloudformation describe-stacks --stack-name "$STACK" \
        --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}
FUNCTION_URL=$(out FunctionUrl)
SITE_BUCKET=$(out SiteBucket)
DISTRIBUTION_ID=$(out DistributionId)
SITE_URL=$(out SiteUrl)

echo "==> Building and uploading the frontend"
cd "$ROOT/frontend"
if [ ! -d node_modules ] || [ package-lock.json -nt node_modules ]; then npm ci; fi
VITE_API_BASE="${FUNCTION_URL%/}" VITE_DEMO_API_KEY="${DEMO_API_KEY:-}" npm run build
aws s3 sync dist/ "s3://$SITE_BUCKET" --delete
aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" --paths '/*' >/dev/null

echo
echo "App: $SITE_URL"
echo "API: $FUNCTION_URL"
