#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${PROJECT_DIR}/logs"
LOG_FILE="${LOG_DIR}/run_$(date +%F).txt"

cd "${PROJECT_DIR}"
mkdir -p "${LOG_DIR}"

if [ ! -f ".venv/bin/activate" ]; then
  echo "未找到 .venv/bin/activate，请先在项目目录创建虚拟环境并安装依赖。" | tee "${LOG_FILE}"
  echo "参考命令：python3 -m venv .venv && source .venv/bin/activate && python -m pip install -r requirements.txt" | tee -a "${LOG_FILE}"
  exit 1
fi

source ".venv/bin/activate"
python3 main.py run 2>&1 | tee "${LOG_FILE}"
