#!/usr/bin/env bash
set -euo pipefail

STACK=${STACK_NAME:-recall}
ROOT=$(cd "$(dirname "$0")" && pwd)
BACKEND=$ROOT/backend
BUILD=$BACKEND/build

command -v aws >/dev/null || { echo "aws CLI not found"; exit 1; }

[ -f "$BACKEND/.env" ] || { echo "backend/.env not found: it holds the credentials, DATABASE_URL and the MCP settings"; exit 1; }
set -a
# shellcheck disable=SC1091
source "$BACKEND/.env"
set +a
: "${DATABASE_URL:?DATABASE_URL is missing from backend/.env}"

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
cp -r "$BACKEND/app" "$BACKEND/seed" "$BACKEND/run.sh" "$BUILD/"
chmod +x "$BUILD/run.sh"
find "$BUILD" -name '__pycache__' -type d -prune -exec rm -rf {} +
echo "    package size: $(du -sh "$BUILD" | cut -f1)  (Lambda limit: 250 MB unzipped)"

echo "==> Deploying the stack"
aws s3api head-bucket --bucket "$STAGING" 2>/dev/null || aws s3 mb "s3://$STAGING" --region "$REGION"
aws cloudformation package \
    --template-file "$BACKEND/template.yaml" \
    --s3-bucket "$STAGING" \
    --output-template-file "$BACKEND/.packaged.yaml" >/dev/null
aws cloudformation deploy \
    --template-file "$BACKEND/.packaged.yaml" \
    --stack-name "$STACK" \
    --capabilities CAPABILITY_IAM \
    --no-fail-on-empty-changeset \
    --parameter-overrides \
        "DatabaseUrl=$DATABASE_URL" \
        "CockroachMcpUrl=${COCKROACH_MCP_URL:-}" \
        "CockroachMcpApiKey=${COCKROACH_MCP_API_KEY:-}" \
        "CockroachMcpClusterId=${COCKROACH_MCP_CLUSTER_ID:-}" \
        "BedrockModelId=${BEDROCK_MODEL_ID:-us.anthropic.claude-sonnet-4-5-20250929-v1:0}" \
        "BedrockEmbeddingModelId=${BEDROCK_EMBEDDING_MODEL_ID:-amazon.titan-embed-text-v2:0}"

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
[ -d node_modules ] || npm ci
VITE_API_BASE="${FUNCTION_URL%/}" npm run build
aws s3 sync dist/ "s3://$SITE_BUCKET" --delete
aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" --paths '/*' >/dev/null

echo
echo "App: $SITE_URL"
echo "API: $FUNCTION_URL"
