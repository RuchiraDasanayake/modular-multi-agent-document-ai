"""
conftest.py — Shared pytest configuration.
"""
import sys
import os

# Ensure ahmn_core packages are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
