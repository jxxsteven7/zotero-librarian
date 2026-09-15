#!/usr/bin/env python3
"""zotero-librarian command-line entry point: python3 zc.py <command> ... (Windows: python zc.py ...). `python3 zc.py --help` lists everything."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zotero_librarian.cli import main
main()
