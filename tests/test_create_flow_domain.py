"""Tests for create flow domain types."""
import pytest
from codogram.domain.create_flow import CreateType


def test_create_type_values():
    assert CreateType.BRANCH.value == "branch"
    assert CreateType.THREAD.value == "thread"


def test_create_type_from_string():
    assert CreateType("branch") == CreateType.BRANCH
    assert CreateType("thread") == CreateType.THREAD
