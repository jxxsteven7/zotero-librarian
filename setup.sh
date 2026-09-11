#!/usr/bin/env bash
# 新机器检查：跑一遍就知道缺什么。不改任何东西。
cd "$(dirname "$0")"
ok=1
if [ -f .env ]; then echo "✓ .env 存在（$(stat -c %a .env)，应为 600）"; else echo "✗ 缺 .env：cp .env.example .env && chmod 600 .env，然后填 key 和数据目录"; ok=0; fi
if command -v pdftotext >/dev/null; then echo "✓ pdftotext"; else echo "✗ 缺 pdftotext：sudo apt install poppler-utils（macOS: brew install poppler）"; ok=0; fi
if command -v python3 >/dev/null; then echo "✓ python3 $(python3 -V 2>&1 | cut -d' ' -f2)（只用标准库）"; else echo "✗ 缺 python3"; ok=0; fi
db=$(python3 -c "import config; print(config.DB)" 2>/dev/null)
if [ -f "$db" ]; then echo "✓ Zotero 库 $db"; else echo "✗ 找不到 $db：改 .env 的 ZOTERO_DATA_DIR（Zotero 设置→高级→文件和文件夹）"; ok=0; fi
if curl -s -m 3 -o /dev/null -w '%{http_code}' -A zotero-claude http://127.0.0.1:23119/connector/ping 2>/dev/null | grep -q 200; then echo "✓ Zotero 桌面端在跑（connector 23119）"; else echo "✗ Zotero 桌面端没开：/download 入库需要它"; ok=0; fi
[ "$ok" = 1 ] && echo "都齐了：在这个目录开 claude，/download <链接>" || exit 1
