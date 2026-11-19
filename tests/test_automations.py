"""Tests for Canonical Automations Draft & Wire Format (D42).

Covers:
- Exhaustive trigger oneof validation (12 proto keys)
- Rejection of invented/paraphrased keys (slackReaction, slack_reaction, slack, reactionAdded)
- Rejection of empty {} triggers
- Slack channel ID constraints:
  - Triggers: C... (public) and G... (private)
  - Actions: C..., G..., and D... (resolves to owner DM)
- Git PR scope: ignoreDraftPrs required, ignoreDraftPr rejected
- YAML prompt block scalar '|' preservation
- Wire format proto JSON generation
- BreakdownBot trigger ingestion and Slack action emission
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from breakdown.automations import (
    EXHAUSTIVE_TRIGGER_KEYS,
    AutomationDraft,
    AutomationWorkflow,
    GitPullRequestScope,
    SlackAction,
    SlackTrigger,
    build_slack_automation_draft,
    build_slack_reaction_automation_draft,
)
from breakdown.bot import BreakdownBot
from breakdown.models import Settings


def test_exhaustive_trigger_keys_accepted() -> None:
    """Each of the 12 canonical trigger oneof keys is accepted when validly structured."""
    for key in EXHAUSTIVE_TRIGGER_KEYS:
        payload: dict[str, str | dict[str, str]]
        if key == "slackTrigger":
            payload = {"channel_id": "C0123456789"}
        elif key == "slackReactionAdded":
            payload = {"channel_id": "C0123456789", "reaction": "eyes"}
        elif key == "slackChannelCreated":
            payload = {"channel_name_prefix": "proj-"}
        elif key == "cron":
            payload = {"schedule": "0 9 * * 1"}
        elif key == "git":
            payload = {"pullRequest": {"ignoreDraftPrs": True}}
        else:
            payload = {"config": "val"}

        workflow = AutomationWorkflow(triggers=({key: payload},))
        assert len(workflow.triggers) == 1
        assert key in workflow.triggers[0]


@pytest.mark.parametrize(
    "bad_key",
    ["slackReaction", "slack_reaction", "slack", "reactionAdded", "my_custom_trigger", "slack_bot"],
)
def test_paraphrased_or_invented_trigger_keys_rejected(bad_key: str) -> None:
    """Paraphrased or invented trigger keys are strictly rejected (they drop in UI)."""
    with pytest.raises(ValueError, match=r"is invalid\. Every trigger must use exactly one"):
        AutomationWorkflow(triggers=({bad_key: {"channel_id": "C01234"}},))


def test_empty_trigger_rejected() -> None:
    """Empty {} trigger entries render as unconfigurable cards in the editor and are rejected."""
    with pytest.raises(ValueError, match="empty or not a dict"):
        AutomationWorkflow(triggers=({},))


def test_multiple_keys_in_single_trigger_rejected() -> None:
    """A trigger object must be a oneof (exactly one top-level key)."""
    with pytest.raises(ValueError, match="exactly one top-level trigger oneof key"):
        AutomationWorkflow(triggers=({"slackTrigger": {"channel_id": "C012"}, "cron": {"schedule": "* * * * *"}},))


@pytest.mark.parametrize("valid_id", ["C01234567", "CABCDEF", "G01234567", "G987654"])
def test_slack_trigger_valid_channel_ids(valid_id: str) -> None:
    """Slack triggers accept public (C...) and private group (G...) channel IDs."""
    trigger = SlackTrigger(channel_id=valid_id)
    assert trigger.channel_id == valid_id


@pytest.mark.parametrize("invalid_id", ["D01234567", "U01234567", "general", "#channel", "random"])
def test_slack_trigger_rejects_dm_and_invalid_channel_ids(invalid_id: str) -> None:
    """Slack triggers reject D... (DM) or non-standard channel names."""
    with pytest.raises(ValueError, match="Must start with 'C'"):
        SlackTrigger(channel_id=invalid_id)


@pytest.mark.parametrize("valid_action_id", ["C01234567", "G01234567", "D01234567"])
def test_slack_action_valid_channel_ids(valid_action_id: str) -> None:
    """Slack actions accept C..., G..., and D... (resolving to owner DM)."""
    action = SlackAction(channel_id=valid_action_id, message="Done.")
    assert action.channel_id == valid_action_id


@pytest.mark.parametrize("invalid_action_id", ["U01234567", "general", ""])
def test_slack_action_rejects_invalid_channel_ids(invalid_action_id: str) -> None:
    """Slack actions reject invalid prefixes."""
    with pytest.raises(ValueError, match="Must start with 'C', 'G', or 'D'"):
        SlackAction(channel_id=invalid_action_id, message="Done.")


def test_git_pull_request_uses_ignore_draft_prs_not_singular() -> None:
    """PR scope enforces 'ignoreDraftPrs', rejecting legacy 'ignoreDraftPr'."""
    scope = GitPullRequestScope(ignoreDraftPrs=True)
    assert scope.ignoreDraftPrs is True

    # When decoded from dict in workflow.triggers:
    with pytest.raises(ValueError, match="Use 'ignoreDraftPrs'"):
        AutomationWorkflow(
            triggers=({"git": {"pullRequest": {"ignoreDraftPr": True}}},)
        )


def test_prompt_uses_block_scalar_pipe() -> None:
    """Prompts containing newlines are formatted with '|' block scalar, not '>-' folding."""
    prompt_text = "Perform repo audit:\n- Check licenses\n- Check dependencies\n- Validate build"
    draft = build_slack_automation_draft(
        name="Audit Automation",
        channel_id="C01234567",
        prompt=prompt_text,
    )
    rendered_yaml = draft.to_yaml()
    # Check that '|' block scalar appears and bullet points are preserved
    assert "|" in rendered_yaml
    assert "- Check licenses" in rendered_yaml


def test_wire_format_proto_json_output() -> None:
    """to_prefill_workflow_data outputs matching proto JSON wire format."""
    draft = build_slack_automation_draft(
        name="Daily Research",
        channel_id="C09988776",
        prompt="Summarize recent changes",
        description="Triggered from Slack research channel",
        response_channel_id="D01234567",
    )
    proto_data = draft.to_prefill_workflow_data()
    assert proto_data["name"] == "Daily Research"
    assert proto_data["workflow"]["triggers"][0]["slackTrigger"]["channel_id"] == "C09988776"
    assert proto_data["workflow"]["actions"][0]["slack"]["channel_id"] == "D01234567"
    assert proto_data["workflow"]["memoryEnabled"] is True
    assert proto_data["workflow"]["agentOptions"]["skipInstall"] is False

    # Check json roundtrip
    as_json = draft.to_json()
    loaded = json.loads(as_json)
    assert loaded["name"] == "Daily Research"


def test_slack_reaction_automation_builder() -> None:
    """build_slack_reaction_automation_draft constructs valid reaction trigger."""
    draft = build_slack_reaction_automation_draft(
        name="Reaction Approval",
        channel_id="C11223344",
        reaction="white_check_mark",
        prompt="Advance workflow upon emoji approval",
    )
    assert len(draft.workflow.triggers) == 1
    trigger_data = draft.workflow.triggers[0]["slackReactionAdded"]
    assert trigger_data["channel_id"] == "C11223344"
    assert trigger_data["reaction"] == "white_check_mark"


def test_bot_parse_slack_trigger_and_action(tmp_path: Path) -> None:
    """BreakdownBot cleanly ingests slackTrigger, parses task and intent, and emits slack action."""
    bot = BreakdownBot.from_settings(Settings(target_repo=tmp_path), offline_demo=True, task_text="research")

    # Ingest mention trigger: <@UBOT123> go research vector search
    parsed = bot.parse_trigger(
        "slackTrigger",
        {
            "channel_id": "C01234567",
            "text": "<@UBOT123> go research vector search",
            "user_id": "UUSER99",
        },
    )
    assert parsed["trigger_key"] == "slackTrigger"
    assert parsed["channel_id"] == "C01234567"
    assert parsed["task"] == "go research vector search"
    assert parsed["intent"]["mode"] == "research"

    # Emit canonical Slack response action
    action = bot.emit_slack_action("C01234567", "Research complete: BaselineMap created.")
    assert action == {
        "slack": {
            "channel_id": "C01234567",
            "message": "Research complete: BaselineMap created.",
        }
    }

    # Emit Slack DM action
    dm_action = bot.emit_slack_action("D0999999", "Your research is ready.")
    assert dm_action["slack"]["channel_id"] == "D0999999"


def test_bot_slack_reaction_trigger_decision(tmp_path: Path) -> None:
    """BreakdownBot interprets white_check_mark reaction as approval."""
    bot = BreakdownBot.from_settings(Settings(target_repo=tmp_path), offline_demo=True, task_text="test")

    parsed = bot.parse_trigger(
        "slackReactionAdded",
        {
            "channel_id": "C01234567",
            "reaction": "white_check_mark",
            "run_id": "dummy_run",
        },
    )
    assert parsed["mapped_action"] == "approve"


def test_automation_yaml_roundtrip_validation(tmp_path: Path) -> None:
    """AutomationDraft saved to YAML validates cleanly through AutomationDraft.model_validate."""
    draft = build_slack_automation_draft(
        name="Roundtrip Test",
        channel_id="C01234567",
        prompt="Step 1: Inspect\nStep 2: Build",
        description="Full roundtrip test",
        response_channel_id="G09876543",
    )
    yaml_text = draft.to_yaml()
    yaml_file = tmp_path / "automation.yaml"
    yaml_file.write_text(yaml_text, encoding="utf-8")

    loaded_dict = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
    validated = AutomationDraft.model_validate(loaded_dict)
    assert validated.name == "Roundtrip Test"
    assert validated.workflow.triggers[0]["slackTrigger"]["channel_id"] == "C01234567"
    assert validated.workflow.actions[0]["slack"]["channel_id"] == "G09876543"


def test_cli_automation_draft_and_validate(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI commands 'automation draft' and 'automation validate' function end-to-end."""
    from breakdown.__main__ import main

    # 1. Draft YAML
    rc = main([
        "automation",
        "draft",
        "--name",
        "CLI Draft",
        "--slack-channel",
        "C01234567",
        "--prompt",
        "Audit codebase",
    ])
    assert rc == 0
    captured = capsys.readouterr()
    assert "name: CLI Draft" in captured.out
    assert "slackTrigger" in captured.out

    # Save to file
    yaml_path = tmp_path / "cli_draft.yaml"
    yaml_path.write_text(captured.out, encoding="utf-8")

    # 2. Validate YAML
    rc_val = main(["automation", "validate", str(yaml_path)])
    assert rc_val == 0
    val_captured = capsys.readouterr()
    assert "automation valid" in val_captured.out

    # 3. Draft JSON wire format
    rc_json = main([
        "automation",
        "draft",
        "--name",
        "CLI JSON Draft",
        "--slack-channel",
        "C01234567",
        "--prompt",
        "Audit codebase",
        "--json",
    ])
    assert rc_json == 0
    json_captured = capsys.readouterr()
    loaded_proto = json.loads(json_captured.out)
    assert loaded_proto["name"] == "CLI JSON Draft"


def test_cli_bot_trigger_execution(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI 'breakdown bot' executes from --trigger payload with offline demo."""
    from breakdown.__main__ import main

    payload = json.dumps({
        "channel_id": "C01234567",
        "text": "go research baseline mapping",
        "user_id": "U12345",
    })

    rc = main([
        "bot",
        "--offline-demo",
        "--auto-approve",
        "--target",
        str(tmp_path),
        "--trigger",
        "slackTrigger",
        "--trigger-payload",
        payload,
    ])
    assert rc == 0
    captured = capsys.readouterr()
    assert "[bot_started]" in captured.out
    assert "[intent_resolved]" in captured.out

