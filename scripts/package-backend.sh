#!/usr/bin/env bash
# 打包後端並上傳到 S3 部署檔 bucket，印出給 runtime stack 用的 AppArtifactKey。
#
# 用法（在 repo 任何位置）：scripts/package-backend.sh
#
# - 只打包「已 commit」的 backend/（用 git archive），所以 .venv、快取、.env 不會被包進去
# - backend/ 有未 commit 的修改時拒絕打包，確保 S3 上的版本對得到 git commit
set -euo pipefail

PROFILE=savebite-lab
REGION=us-east-1

cd "$(git rev-parse --show-toplevel)"

if [ -n "$(git status --porcelain -- backend)" ]; then
  echo "錯誤：backend/ 有未 commit 的修改，請先 commit 再打包。" >&2
  exit 1
fi

ARN=$(aws sts get-caller-identity --profile "$PROFILE" --query Arn --output text)
case "$ARN" in
  *assumed-role/voclabs/*) ;;
  *) echo "錯誤：目前身分不是 Learner Lab（$ARN），停止。" >&2; exit 1 ;;
esac

BUCKET=$(aws cloudformation describe-stacks --profile "$PROFILE" --region "$REGION" \
  --stack-name savebite-base \
  --query "Stacks[0].Outputs[?OutputKey=='ArtifactBucketName'].OutputValue" --output text)
SHA=$(git rev-parse --short=12 HEAD)
KEY="releases/backend-${SHA}.tar.gz"
TMP=$(mktemp -t savebite-backend).tar.gz

git archive --format=tar.gz -o "$TMP" HEAD backend
aws s3 cp "$TMP" "s3://${BUCKET}/${KEY}" --profile "$PROFILE" --region "$REGION" --only-show-errors
rm -f "$TMP"

echo "已上傳 s3://${BUCKET}/${KEY}"
echo "AppArtifactKey=${KEY}"
