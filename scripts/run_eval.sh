#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Evaluation runner with structured logging, metadata capture, and model comparison support.
#
# Usage:
#   ./scripts/run_eval.sh --config <config_file> [--run-id <id>] [--tag <tag>]
#
# Examples:
#   ./scripts/run_eval.sh --config frontends/benchmarks/freshqa/configs/config_shallow_research_only.yml --tag nim-nemotron
#   ./scripts/run_eval.sh --config frontends/benchmarks/freshqa/configs/config_shallow_research_only.yml --tag vllm-qwen3

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Defaults
CONFIG_FILE=""
RUN_ID=""
TAG=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --config) CONFIG_FILE="$2"; shift 2 ;;
        --run-id) RUN_ID="$2"; shift 2 ;;
        --tag)    TAG="$2"; shift 2 ;;
        --help|-h)
            echo "Usage: $0 --config <config_file> [--run-id <id>] [--tag <tag>]"
            echo ""
            echo "Options:"
            echo "  --config <path>   Path to NAT eval config file (required)"
            echo "  --run-id <id>     Custom run ID (default: auto-generated timestamp)"
            echo "  --tag <tag>       Tag for this run (e.g., model name, experiment label)"
            echo ""
            echo "Output goes to: eval_runs/<run_id>/"
            exit 0 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [ -z "$CONFIG_FILE" ]; then
    echo "Error: --config is required"
    exit 1
fi

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Config file not found: $CONFIG_FILE"
    exit 1
fi

# Generate run ID
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
if [ -z "$RUN_ID" ]; then
    BENCHMARK=$(basename "$(dirname "$(dirname "$CONFIG_FILE")")")
    CONFIG_NAME=$(basename "$CONFIG_FILE" .yml)
    TAG_SUFFIX=""
    if [ -n "$TAG" ]; then
        TAG_SUFFIX="_${TAG}"
    fi
    RUN_ID="${BENCHMARK}_${CONFIG_NAME}${TAG_SUFFIX}_${TIMESTAMP}"
fi

# Create run directory
RUN_DIR="$PROJECT_ROOT/eval_runs/$RUN_ID"
mkdir -p "$RUN_DIR"

echo "================================================"
echo "Evaluation Run: $RUN_ID"
echo "================================================"
echo ""
echo "Config:    $CONFIG_FILE"
echo "Tag:       ${TAG:-none}"
echo "Run Dir:   $RUN_DIR"
echo "Timestamp: $TIMESTAMP"
echo ""

# Load environment
if [ -f "$PROJECT_ROOT/deploy/.env" ]; then
    set -a
    source "$PROJECT_ROOT/deploy/.env"
    set +a
    echo "Environment loaded from deploy/.env"
fi

# Capture run metadata
cat > "$RUN_DIR/metadata.json" << METADATA
{
    "run_id": "$RUN_ID",
    "config_file": "$CONFIG_FILE",
    "tag": "${TAG:-}",
    "timestamp": "$TIMESTAMP",
    "start_time": "$(date -Iseconds)",
    "git_branch": "$(git -C "$PROJECT_ROOT" branch --show-current 2>/dev/null || echo 'unknown')",
    "git_commit": "$(git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo 'unknown')",
    "python_version": "$(python --version 2>&1)",
    "env": {
        "NVIDIA_API_KEY": "${NVIDIA_API_KEY:+set}",
        "TAVILY_API_KEY": "${TAVILY_API_KEY:+set}",
        "OPENAI_API_KEY": "${OPENAI_API_KEY:+set}",
        "SERPER_API_KEY": "${SERPER_API_KEY:+set}"
    }
}
METADATA

# Copy config for reproducibility
cp "$CONFIG_FILE" "$RUN_DIR/config.yml"

echo "Metadata saved to $RUN_DIR/metadata.json"
echo "Config copied to $RUN_DIR/config.yml"
echo ""
echo "================================================"
echo "Starting nat eval..."
echo "================================================"
echo ""

# Run evaluation with full logging
# Tee output to both console and log file
dotenv -f "$PROJECT_ROOT/deploy/.env" run \
    nat eval --config_file "$CONFIG_FILE" 2>&1 | tee "$RUN_DIR/eval.log"

EXIT_CODE=${PIPESTATUS[0]}

# Copy results to run directory
CONFIG_OUTPUT_DIR=$(python3 -c "
import yaml
with open('$CONFIG_FILE') as f:
    c = yaml.safe_load(f)
print(c.get('eval', {}).get('general', {}).get('output_dir', ''))
" 2>/dev/null)

if [ -n "$CONFIG_OUTPUT_DIR" ] && [ -d "$PROJECT_ROOT/$CONFIG_OUTPUT_DIR" ]; then
    echo ""
    echo "Copying results from $CONFIG_OUTPUT_DIR to $RUN_DIR/results/"
    cp -r "$PROJECT_ROOT/$CONFIG_OUTPUT_DIR" "$RUN_DIR/results/"
fi

# Update metadata with end time and exit code
python3 -c "
import json
with open('$RUN_DIR/metadata.json') as f:
    meta = json.load(f)
meta['end_time'] = '$(date -Iseconds)'
meta['exit_code'] = $EXIT_CODE
meta['status'] = 'completed' if $EXIT_CODE == 0 else 'failed'
with open('$RUN_DIR/metadata.json', 'w') as f:
    json.dump(meta, f, indent=2)
"

echo ""
echo "================================================"
echo "Evaluation Complete"
echo "================================================"
echo ""
echo "Run ID:    $RUN_ID"
echo "Status:    $([ $EXIT_CODE -eq 0 ] && echo 'SUCCESS' || echo 'FAILED')"
echo "Results:   $RUN_DIR/"
echo "Log:       $RUN_DIR/eval.log"
echo "Metadata:  $RUN_DIR/metadata.json"
echo ""

exit $EXIT_CODE
