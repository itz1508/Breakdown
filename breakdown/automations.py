"""Canonical Automations Draft & Wire Format (D42).

Implements the official Antigravity Automations draft YAML output shape and
proto wire format (`prefillWorkflowData` passed to `open_automation`).

Exhaustive Trigger Oneof Keys:
- cron
- git
- slackTrigger
- slackReactionAdded
- slackChannelCreated
- emailReceived
- microsoftTeamsTrigger
- microsoftTeamsChannelCreated
- linear
- webhook
- pagerduty
- sentry

Never invent or paraphrase trigger keys (e.g. `slackReaction`, `slack_reaction`,
`slack`, `reactionAdded`) — the editor decodes triggers with `ignoreUnknownFields: true`,
silently dropping unknown keys into an unconfigurable card that blocks save.

Slack channel ID validation:
- Triggers (`slackTrigger`, `slackReactionAdded`): `C…` (public) or `G…` (private group/channel).
- Actions (`slack` action): `C…`, `G…`, or `D…` (resolves to automation owner's DM).

Git PR validation:
- Uses `ignoreDraftPrs` (not `ignoreDraftPr`).
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

# The 12 exhaustive top-level trigger oneof keys accepted by the Automations editor.
EXHAUSTIVE_TRIGGER_KEYS: frozenset[str] = frozenset({
    "cron",
    "git",
    "slackTrigger",
    "slackReactionAdded",
    "slackChannelCreated",
    "emailReceived",
    "microsoftTeamsTrigger",
    "microsoftTeamsChannelCreated",
    "linear",
    "webhook",
    "pagerduty",
    "sentry",
})

SLACK_TRIGGER_KEYS: frozenset[str] = frozenset({
    "slackTrigger",
    "slackReactionAdded",
    "slackChannelCreated",
})

_SLACK_CHANNEL_REGEX = re.compile(r"^[CG][A-Z0-9]+$")
_SLACK_ACTION_CHANNEL_REGEX = re.compile(r"^[CGD][A-Z0-9]+$")


class _StrictAutomationModel(BaseModel):
    """Base model for Automations with strict extra forbidding, without schema_version."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class SlackTrigger(_StrictAutomationModel):
    """Trigger on Slack mentions, messages, or channel events."""

    channel_id: str = Field(description="Slack channel ID starting with C or G")
    keywords: tuple[str, ...] = ()
    filter_user_ids: tuple[str, ...] = ()

    @field_validator("channel_id")
    @classmethod
    def validate_channel_id(cls, v: str) -> str:
        if not _SLACK_CHANNEL_REGEX.match(v):
            raise ValueError(
                f"Invalid Slack trigger channel ID {v!r}. Must start with 'C' (public) or 'G' (private group)."
            )
        return v


class SlackReactionAddedTrigger(_StrictAutomationModel):
    """Trigger when a specific reaction is added to a message."""

    channel_id: str = Field(description="Slack channel ID starting with C or G")
    reaction: str = Field(min_length=1, description="Reaction emoji name, e.g. 'white_check_mark', 'eyes'")

    @field_validator("channel_id")
    @classmethod
    def validate_channel_id(cls, v: str) -> str:
        if not _SLACK_CHANNEL_REGEX.match(v):
            raise ValueError(
                f"Invalid Slack trigger channel ID {v!r}. Must start with 'C' (public) or 'G' (private group)."
            )
        return v


class SlackChannelCreatedTrigger(_StrictAutomationModel):
    """Trigger when a new Slack channel is created."""

    channel_name_prefix: str = ""


class SlackAction(_StrictAutomationModel):
    """Slack message emission action.

    Channel ID must start with:
    - 'C': public channel
    - 'G': private group / channel
    - 'D': automation owner's direct message (DM)
    """

    channel_id: str = Field(description="Slack destination channel ID (C…, G…, or D…)")
    message: str = Field(min_length=1)
    thread_ts: str | None = None

    @field_validator("channel_id")
    @classmethod
    def validate_channel_id(cls, v: str) -> str:
        if not _SLACK_ACTION_CHANNEL_REGEX.match(v):
            raise ValueError(
                f"Invalid Slack action channel ID {v!r}. Must start with 'C', 'G', or 'D' (resolves to owner's DM)."
            )
        return v


class GitPullRequestScope(_StrictAutomationModel):
    """PR scope for git triggers."""

    repos: tuple[str, ...] = ()
    orgs: tuple[str, ...] = ()
    ignoreDraftPrs: bool = True
    actions: tuple[
        Literal[
            "GIT_PULL_REQUEST_ACTION_OPENED",
            "GIT_PULL_REQUEST_ACTION_CLOSED",
            "GIT_PULL_REQUEST_ACTION_SYNCHRONIZE",
            "GIT_PULL_REQUEST_ACTION_REOPENED",
        ],
        ...,
    ] = ("GIT_PULL_REQUEST_ACTION_OPENED",)


class GitTrigger(_StrictAutomationModel):
    """Git event trigger."""

    pullRequest: GitPullRequestScope | None = None


class GitConfig(_StrictAutomationModel):
    """Checkout configuration for non-git triggers needing a workspace."""

    repo: str = Field(min_length=1)
    branch: str = "main"


class AgentOptions(_StrictAutomationModel):
    """Agent execution settings."""

    skipInstall: bool = False


class AutomationWorkflow(_StrictAutomationModel):
    """The workflow structure containing triggers, actions, prompts, and options."""

    triggers: tuple[dict[str, Any], ...] = ()
    actions: tuple[dict[str, Any], ...] = ()
    prompts: tuple[str, ...] = ()
    model: str = ""
    agentOptions: AgentOptions = Field(default_factory=AgentOptions)
    memoryEnabled: bool = True
    gitConfig: GitConfig | None = None

    @field_validator("triggers")
    @classmethod
    def validate_triggers(cls, triggers: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
        for idx, trigger in enumerate(triggers):
            if not isinstance(trigger, dict) or not trigger:
                raise ValueError(
                    f"Trigger at index {idx} is empty or not a dict. "
                    "Empty trigger entries render as an unconfigurable card in the editor."
                )
            keys = set(trigger.keys())
            if len(keys) != 1:
                raise ValueError(
                    f"Trigger at index {idx} must have exactly one top-level trigger oneof key, got {sorted(keys)!r}."
                )
            key = next(iter(keys))
            if key not in EXHAUSTIVE_TRIGGER_KEYS:
                raise ValueError(
                    f"Trigger key {key!r} is invalid. Every trigger must use exactly one of the "
                    f"exhaustive proto keys: {sorted(EXHAUSTIVE_TRIGGER_KEYS)!r}. "
                    "Never invent or paraphrase trigger keys (e.g. 'slackReaction', 'slack_reaction', 'slack')."
                )
            # Detailed validation for Slack triggers
            payload = trigger[key]
            if isinstance(payload, dict):
                if key == "slackTrigger":
                    SlackTrigger.model_validate(payload)
                elif key == "slackReactionAdded":
                    SlackReactionAddedTrigger.model_validate(payload)
                elif key == "slackChannelCreated":
                    SlackChannelCreatedTrigger.model_validate(payload)
                elif key == "git" and "pullRequest" in payload:
                    pr = payload["pullRequest"]
                    if isinstance(pr, dict):
                        if "ignoreDraftPr" in pr:
                            msg = "Invalid field 'ignoreDraftPr' in git.pullRequest. Use 'ignoreDraftPrs'."
                            raise ValueError(msg)
                        GitPullRequestScope.model_validate(pr)
        return triggers

    @field_validator("actions")
    @classmethod
    def validate_actions(cls, actions: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
        for idx, action in enumerate(actions):
            if not isinstance(action, dict):
                raise ValueError(f"Action at index {idx} must be a dict.")
            # Empty action dicts are valid when the field is UI-only.
            if "slack" in action:
                slack_payload = action["slack"]
                if isinstance(slack_payload, dict):
                    SlackAction.model_validate(slack_payload)
        return actions


class AutomationDraft(_StrictAutomationModel):
    """Authoritative Automations Draft matching the open_automation wire format."""

    name: str = Field(min_length=1)
    description: str = ""
    workflow: AutomationWorkflow = Field(default_factory=AutomationWorkflow)

    def to_yaml(self) -> str:
        """Render to reviewed Automations draft YAML using | block scalar for prompts."""
        raw_dict = self.model_dump(exclude_none=True)

        class _LiteralDumper(yaml.SafeDumper):
            pass

        def _str_presenter(dumper: yaml.SafeDumper, data: str) -> yaml.Node:
            if "\n" in data:
                return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
            return dumper.represent_scalar("tag:yaml.org,2002:str", data)

        _LiteralDumper.add_representer(str, _str_presenter)
        return yaml.dump(raw_dict, Dumper=_LiteralDumper, sort_keys=False, default_flow_style=False)

    def to_prefill_workflow_data(self) -> dict[str, Any]:
        """Produce canonical proto JSON dictionary passed to open_automation."""
        return self.model_dump(exclude_none=True)

    def to_json(self, *, indent: int = 2) -> str:
        """Produce canonical proto JSON string."""
        return json.dumps(self.to_prefill_workflow_data(), indent=indent)


def build_slack_automation_draft(
    name: str,
    channel_id: str,
    prompt: str,
    *,
    description: str = "",
    keywords: tuple[str, ...] = (),
    model: str = "",
    memory_enabled: bool = True,
    response_channel_id: str | None = None,
) -> AutomationDraft:
    """Helper to build a valid Slack-triggered automation draft."""
    slack_trigger = SlackTrigger(channel_id=channel_id, keywords=keywords)
    actions: list[dict[str, Any]] = []
    if response_channel_id:
        action_obj = SlackAction(channel_id=response_channel_id, message="Automation finished.")
        actions.append({"slack": action_obj.model_dump()})

    workflow = AutomationWorkflow(
        triggers=({"slackTrigger": slack_trigger.model_dump(exclude_none=True)},),
        actions=tuple(actions),
        prompts=(prompt,),
        model=model,
        agentOptions=AgentOptions(skipInstall=False),
        memoryEnabled=memory_enabled,
    )
    return AutomationDraft(name=name, description=description, workflow=workflow)


def build_slack_reaction_automation_draft(
    name: str,
    channel_id: str,
    reaction: str,
    prompt: str,
    *,
    description: str = "",
    model: str = "",
    memory_enabled: bool = True,
) -> AutomationDraft:
    """Helper to build a valid Slack reaction-triggered automation draft."""
    reaction_trigger = SlackReactionAddedTrigger(channel_id=channel_id, reaction=reaction)
    workflow = AutomationWorkflow(
        triggers=({"slackReactionAdded": reaction_trigger.model_dump(exclude_none=True)},),
        actions=(),
        prompts=(prompt,),
        model=model,
        agentOptions=AgentOptions(skipInstall=False),
        memoryEnabled=memory_enabled,
    )
    return AutomationDraft(name=name, description=description, workflow=workflow)
