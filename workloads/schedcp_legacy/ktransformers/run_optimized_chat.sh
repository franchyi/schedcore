#!/bin/bash
"""
Shell script to run optimized local chat with LD_PRELOAD=./liba.so
"""

# Default parameters - can be overridden by command line arguments
MODEL_PATH="${1:-unsloth/DeepSeek-R1}"
GGUF_PATH="${2:-/root/deepseek-gguf/}"
OPTIMIZE_CONFIG_PATH="${3:-optimize/optimize_rules/DeepSeek-V3-Chat-int8-fast.yaml}"
BATCH_SIZE="${4:-32}"
SPECULATIVE_LENGTH="${5:-6}"

echo "Running optimized local chat with LD_PRELOAD=./liba.so"
echo "Model path: $MODEL_PATH"
echo "GGUF path: $GGUF_PATH"
echo "Optimize config: $OPTIMIZE_CONFIG_PATH"
echo "Batch size: $BATCH_SIZE"
echo "Speculative length: $SPECULATIVE_LENGTH"
echo ""

# Run the command with LD_PRELOAD
LD_PRELOAD=./liba.so python optimized_local_chat.py \
    --model_path="$MODEL_PATH" \
    --gguf_path="$GGUF_PATH" \
    --optimize_config_path="$OPTIMIZE_CONFIG_PATH" \
    --batch_size="$BATCH_SIZE" \
    --speculative_length="$SPECULATIVE_LENGTH"