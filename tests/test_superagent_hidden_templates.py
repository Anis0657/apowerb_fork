"""Templates hidden from the Create Agent picker by configuration.

A deployment may not want to offer every template yet. It lists the
template ids to hide in ``SUPERAGENT_HIDDEN_TEMPLATES`` (comma-separated).
Hiding is a picker concern only:

  - the list served to a signed-in user drops those ids,
  - an agent already created from a hidden template still resolves its
    template, by the internal path (``user=None``) and by the id route,
  - with the setting empty, the picker is exactly what it was.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apowerb.configs.settings import get_settings
from apowerb.core.superagents import (
    get_superagent_template,
    list_superagent_templates,
)

USER = SimpleNamespace(email="someone@example.com")


def _ids(templates):
    return [t["template_id"] for t in templates]


@pytest.fixture
def hide(monkeypatch):
    def _hide(value: str):
        monkeypatch.setattr(
            get_settings(), "superagent_hidden_templates", value, raising=False
        )

    return _hide


def test_hidden_templates_leave_the_picker(hide):
    hide("dashboard_agent, image_creator")
    ids = _ids(list_superagent_templates(user=USER))
    assert "dashboard_agent" not in ids
    assert "image_creator" not in ids
    assert "rag_agent" in ids


def test_empty_setting_keeps_the_picker_unchanged(hide):
    hide("")
    assert _ids(list_superagent_templates(user=USER)) == _ids(
        list_superagent_templates(user=None)
    )


def test_an_agent_built_from_a_hidden_template_still_resolves_it(hide):
    hide("dashboard_agent")
    assert get_superagent_template("dashboard_agent", user=None) is not None
    assert get_superagent_template("dashboard_agent", user=USER) is not None


def test_system_callers_still_get_the_full_catalog(hide):
    hide("dashboard_agent")
    assert "dashboard_agent" in _ids(list_superagent_templates(user=None))


def test_unknown_or_blank_entries_are_ignored(hide):
    hide(" , not_a_template,,")
    assert _ids(list_superagent_templates(user=USER)) == _ids(
        list_superagent_templates(user=None)
    )
