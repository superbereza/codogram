# tests/domain/test_setup_models.py
import pytest
from codogram.domain.setup_models import SetupContext


def test_setup_context_has_all_fields():
    """SetupContext has all required fields."""
    ctx = SetupContext(
        setup_type="clone",
        project_name="my-project",
    )
    assert ctx.setup_type == "clone"
    assert ctx.project_name == "my-project"
    assert ctx.clone_url is None
    assert ctx.target_dir is None
    assert ctx.rename_to is None


def test_setup_context_from_dict():
    """SetupContext can be created from dict (FSM data)."""
    data = {"setup_type": "connect", "project_name": "test"}
    ctx = SetupContext.from_dict(data)
    assert ctx.setup_type == "connect"


def test_setup_context_to_dict():
    """SetupContext can be converted to dict for FSM."""
    ctx = SetupContext(setup_type="new", project_name="foo")
    data = ctx.to_dict()
    assert data["setup_type"] == "new"
    assert data["project_name"] == "foo"
