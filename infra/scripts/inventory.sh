#!/usr/bin/env bash
# AWS sandbox inventory (plan 15.1, T1.8). READ-ONLY checks: records allowed / denied per capability to docs/AWS_INVENTORY.md.
# Usage:  AWS_REGION=us-east-1 bash infra/scripts/inventory.sh [region ...]
# Needs the AWS CLI configured with the temporary credentials from the Workshop Studio console (docs/HUMAN_TASKS.md H-01).
# It never creates resources. Creation permissions (EC2 run-instances, CloudFormation, IAM roles) are checked with --dry-run
# or template validation only, and a human must approve any throwaway-resource test separately.
set -u
OUT="docs/AWS_INVENTORY.md"
REGIONS=("$@"); [ ${#REGIONS[@]} -eq 0 ] && REGIONS=("${AWS_REGION:-us-east-1}")

if ! command -v aws >/dev/null 2>&1; then
  echo "AWS CLI not found. Install it (https://aws.amazon.com/cli/), configure credentials, then re-run." >&2
  exit 2
fi

row() { # name, command...  -> prints a markdown row with allowed/denied and the first line of any error
  local name="$1"; shift
  local out rc
  out=$("$@" 2>&1); rc=$?
  if [ $rc -eq 0 ]; then echo "| $name | allowed | |"
  else echo "| $name | **denied / failed** | $(echo "$out" | head -n1 | tr '|' '/' | cut -c1-140) |"; fi
}

{
  echo "# AWS sandbox inventory"
  echo
  echo "Generated $(date -u +%Y-%m-%dT%H:%M:%SZ) by infra/scripts/inventory.sh (read-only). Account and caller:"
  echo
  echo '```'
  aws sts get-caller-identity 2>&1
  echo '```'
  for R in "${REGIONS[@]}"; do
    echo
    echo "## Region $R"
    echo
    echo "| Capability | Result | First error line |"
    echo "|---|---|---|"
    row "ec2 describe-regions" aws ec2 describe-regions --region "$R"
    row "ec2 instance type offerings (c7i/c6i/m7i/t3/g4dn/g5)" aws ec2 describe-instance-type-offerings --region "$R" --filters "Name=instance-type,Values=c7i.xlarge,c6i.xlarge,m7i.xlarge,t3.xlarge,g4dn.xlarge,g5.xlarge"
    row "ec2 run-instances --dry-run (t3.small)" aws ec2 run-instances --region "$R" --dry-run --instance-type t3.small --image-id ami-00000000
    row "cloudformation validate-template" aws cloudformation validate-template --region "$R" --template-body file://infra/cloudformation/kiosk-stack.yaml
    row "cloudformation list-stacks" aws cloudformation list-stacks --region "$R"
    row "cloudfront list-distributions" aws cloudfront list-distributions
    row "ecr describe-repositories" aws ecr describe-repositories --region "$R"
    row "dynamodb list-tables" aws dynamodb list-tables --region "$R"
    row "s3 ls" aws s3 ls
    row "kms list-keys" aws kms list-keys --region "$R"
    row "iam list-roles (read)" aws iam list-roles --max-items 1
    row "rekognition list-collections" aws rekognition list-collections --region "$R"
    row "ssm describe-parameters" aws ssm describe-parameters --region "$R" --max-results 1
  done
  echo
  echo "## Still to record by hand"
  echo
  echo "- Account lifetime and what is wiped afterwards (ask the organizers; HUMAN_TASKS H-01/H-02)."
  echo "- Round-trip time from the venue network to each allowed region (tools/net_probe.py)."
  echo "- Whether Rekognition Face Liveness is permitted (benchmark only; P2)."
} | tee "$OUT"
