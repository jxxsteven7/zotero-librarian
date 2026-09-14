#!/usr/bin/env python3
"""zotero-claude 命令行入口：python3 zc.py <命令> …（Windows：python zc.py …）。`python3 zc.py --help` 看全部命令。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zotero_claude.cli import main
main()
