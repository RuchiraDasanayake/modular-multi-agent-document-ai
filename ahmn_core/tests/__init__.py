"""
conftest.py — Shared pytest fixtures for AHMN unit tests.
"""
import sys
import os
import pytest

# Ensure ahmn_core is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
