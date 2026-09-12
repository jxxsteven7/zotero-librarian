#!/usr/bin/env bash
# 新机器体检的薄包装：挑一个能用的 Python 跑 setup.py（Linux/macOS 叫 python3，Windows Git Bash 里常只有 python）。
cd "$(dirname "$0")" || exit 1
for py in python3 python py; do
  if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
    exec "$py" setup.py "$@"
  fi
done
echo "✗ 没找到 Python 3.8+：Ubuntu sudo apt install python3；macOS brew install python；Windows 装 python.org 安装包并勾选 Add to PATH"; exit 1
