"""Grok Bot / Cursor cloud-agent transcripts → scrubbed T0 events.

Local Cursor T0 already reads usage-shaped `~/.cursor/**/*.jsonl` and skips
`agent-transcripts` (those files are usually prompt-only). Named Grok Bot /
cloud-agent runs live outside that tree (`agent-data`, exported
`transcript.json` + `index.json`). This adapter reads configurable roots and
reuses `ardoise.attribution` — it never invents agent/skill/effort.

Fail-open: unreadable or unknown shapes are skipped. Prompts are scrubbed
before upsert. Stdlib only. No credentials.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterator

from ardoise.adapters.hook_event import event_to_entry
from ardoise.attribution import DIMENSIONS, extract
from ardoise.model import extract_model, is_placeholder
from ardoise.vendors.anthropic import parse_t0_line
from ardoise.vendors.cursor import parse_cursor_line
from ardoise.vendors.jsonl import iter_jsonl

SOURCE = "cursor"
VENDOR = "cursor"

_FILE_NAMES = frozenset(
    {
        "transcript.json",
        "transcript.jsonl",
        "events.json",
        "events.jsonl",
        "usage.json",
        "usage.jsonl",
        "index.json",
        "run.json",
        "agent.json",
        "meta.json",
    }
)
_LIST_KEYS = (
    "messages",
    "events",
    "runs",
    "usageEvents",
    "usage_events",
    "transcript",
)
_SKIP_NAMES = frozenset(
    {".env", "credentials.json", "secrets.json", "credentials", "secrets"}
)
_SKIP_PARTS = frozenset({".git", "node_modules", "__pycache__"})
_SIDECARS = ("index.json", "run.json", "agent.json", "meta.json")
_ENV_ROOTS = ("ARDOISE_CLOUD_AGENT_ROOT", "ARDOISE_AGENT_DATA")
_RUN_ID_KEYS = (
    "sessionId",
    "session_id",
    "conversation_id",
    "conversationId",
    "bcId",
    "bc_id",
    "cloudAgentId",
    "cloud_agent_id",
)


def _person() -> str:
    raw = os.environ.get("ARDOISE_PERSON")
    return raw.strip() if raw and raw.strip() else ""


def looks_like_run_meta(obj: dict[str, Any] | None) -> bool:
    """Cloud-agent index/run wrappers name a *job*, not an agent identity."""
    if not isinstance(obj, dict):
        return False
    hints = {"status", "env", "repos", "latestRunId", "latest_run_id"}
    if hints & set(obj):
        return True
    ident = str(obj.get("id") or obj.get("bcId") or obj.get("bc_id") or "")
    return ident.startswith("bc-")


def _has_direct_usage(obj: dict[str, Any]) -> bool:
    if isinstance(obj.get("usage"), dict):
        return True
    if isinstance(obj.get("tokenUsage"), dict) or isinstance(obj.get("token_usage"), dict):
        return True
    message = obj.get("message")
    if isinstance(message, dict) and isinstance(message.get("usage"), dict):
        return True
    for key in (
        "input_tokens",
        "inputTokens",
        "output_tokens",
        "outputTokens",
        "cache_read_tokens",
        "cacheReadTokens",
    ):
        if obj.get(key) not in (None, "", 0, "0"):
            return True
    return False


def _normalized_usage(obj: dict[str, Any]) -> dict[str, int]:
    usage = obj.get("usage")
    if not isinstance(usage, dict):
        usage = obj.get("tokenUsage") or obj.get("token_usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    message = obj.get("message") if isinstance(obj.get("message"), dict) else {}
    nested = message.get("usage") if isinstance(message.get("usage"), dict) else {}

    def _pick(*keys: str) -> int:
        for key in keys:
            if key in usage and usage.get(key) not in (None, ""):
                try:
                    return int(usage.get(key) or 0)
                except (TypeError, ValueError):
                    return 0
            if key in nested and nested.get(key) not in (None, ""):
                try:
                    return int(nested.get(key) or 0)
                except (TypeError, ValueError):
                    return 0
            if key in obj and obj.get(key) not in (None, ""):
                try:
                    return int(obj.get(key) or 0)
                except (TypeError, ValueError):
                    return 0
        return 0

    return {
        "input_tokens": _pick("input_tokens", "inputTokens"),
        "output_tokens": _pick("output_tokens", "outputTokens"),
        "cache_creation_input_tokens": _pick(
            "cache_creation_input_tokens",
            "cacheWriteTokens",
            "cache_write_tokens",
            "cache_creation_tokens",
        ),
        "cache_read_input_tokens": _pick(
            "cache_read_input_tokens",
            "cacheReadTokens",
            "cache_read_tokens",
        ),
    }


def _run_id_values(data: dict[str, Any] | None) -> list[str]:
    """Stable conversation / cloud-agent run ids. Never treats a job title as an id."""
    found: list[str] = []
    seen: set[str] = set()

    def _add(raw: Any) -> None:
        if not isinstance(raw, str):
            return
        text = raw.strip()
        if not text or text in seen:
            return
        seen.add(text)
        found.append(text)

    if not isinstance(data, dict):
        return found
    layers: list[dict[str, Any]] = [data]
    nested = data.get("agent")
    if isinstance(nested, dict):
        layers.append(nested)
    for layer in layers:
        for key in _RUN_ID_KEYS:
            _add(layer.get(key))
        ident = layer.get("id")
        if isinstance(ident, str) and ident.strip().startswith("bc-"):
            _add(ident)
    return found


def _meta_from(data: dict[str, Any]) -> dict[str, Any]:
    """Sidecar identity only — never the run title (`name`)."""
    attrs = extract(data)
    out: dict[str, Any] = {}
    for key in DIMENSIONS:
        if attrs.get(key):
            out[key] = attrs[key]
    ids = _run_id_values(data)
    if ids:
        out["session_id"] = ids[0]
    model = extract_model(data)
    if model:
        out["model"] = model
    for key in ("createdAt", "created_at", "timestamp", "occurred_at"):
        if data.get(key):
            out["timestamp"] = data.get(key)
            break
    cwd = data.get("cwd")
    if cwd:
        out["cwd"] = cwd
    return out


def sidecar_meta(path: Path) -> dict[str, Any]:
    parent = path.parent
    for name in _SIDECARS:
        cand = parent / name
        if cand.resolve() == path.resolve() or not cand.is_file():
            continue
        try:
            data = json.loads(cand.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            continue
        if isinstance(data, dict):
            return _meta_from(data)
    return {}


def iter_transcript_objects(path: Path) -> Iterator[dict[str, Any]]:
    """Yield dicts from JSONL, a JSON array, or a JSON object with a list key."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    stripped = text.lstrip()
    if not stripped:
        return
    if stripped[0] in "[{":
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    yield item
            return
        if isinstance(data, dict):
            yielded = False
            for key in _LIST_KEYS:
                seq = data.get(key)
                if isinstance(seq, list) and seq:
                    for item in seq:
                        if isinstance(item, dict):
                            yield item
                            yielded = True
                    break
            if not yielded:
                yield data
            return
    yield from iter_jsonl(path)


def _from_usage_shaped(obj: dict[str, Any]) -> dict[str, Any] | None:
    usage = _normalized_usage(obj)
    if not any(usage.values()):
        return None
    message = obj.get("message") if isinstance(obj.get("message"), dict) else {}
    model = extract_model(obj, message)
    wrapped = {
        "type": obj.get("type") or "assistant",
        "model": model,
        "model_id": obj.get("model_id") or obj.get("modelId") or message.get("model_id") or message.get("modelId"),
        "cwd": obj.get("cwd"),
        "timestamp": obj.get("timestamp") or obj.get("ts") or obj.get("occurred_at"),
        "sessionId": obj.get("sessionId") or obj.get("session_id") or obj.get("conversationId"),
        "requestId": obj.get("requestId") or obj.get("request_id") or obj.get("generation_id"),
        "message_id": obj.get("message_id") or obj.get("messageId") or message.get("id") or obj.get("id"),
        "uuid": obj.get("uuid"),
        "usage": usage,
        "message": {
            "id": message.get("id") or obj.get("message_id") or obj.get("id"),
            "model": model or message.get("model"),
            "role": message.get("role") or "assistant",
            "usage": usage,
        },
        "agent": obj.get("agent"),
        "agentName": obj.get("agentName") or obj.get("agent_name"),
        "botName": obj.get("botName") or obj.get("bot_name") or obj.get("bot"),
        "skill": obj.get("skill"),
        "effort": obj.get("effort"),
        "attribution": obj.get("attribution"),
        "metadata": obj.get("metadata"),
        "model_params": obj.get("model_params") or obj.get("modelParams"),
    }
    return event_to_entry(wrapped, default_source=SOURCE)


def parse_line(obj: dict[str, Any] | None, *, inherited: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Parse one transcript object. Fail-open. Never invent attribution."""
    if not isinstance(obj, dict):
        return None
    try:
        if looks_like_run_meta(obj) and not _has_direct_usage(obj):
            return None
        merged = dict(inherited or {})
        merged.update(obj)
        entry = parse_t0_line(merged) or parse_cursor_line(merged)
        if not entry:
            entry = _from_usage_shaped(merged)
        if not entry:
            return None
        attrs = extract(obj)
        inherited_attrs = extract(inherited) if inherited else {}
        for key in DIMENSIONS:
            if not entry.get(key):
                entry[key] = attrs.get(key) or inherited_attrs.get(key)
        model = str(entry.get("model") or merged.get("model") or "").lower()
        if "claude" in model or "anthropic" in model:
            entry.setdefault("vendor", "anthropic")
            entry.setdefault("source", "anthropic_t0")
        else:
            entry["source"] = SOURCE
            entry["vendor"] = VENDOR
        entry["tier"] = "T0"
        if not entry.get("person"):
            entry["person"] = _person()
        if inherited:
            if not entry.get("session_id") and inherited.get("session_id"):
                entry["session_id"] = inherited.get("session_id")
            if is_placeholder(entry.get("model")) and inherited.get("model") and not is_placeholder(
                inherited.get("model")
            ):
                entry["model"] = inherited.get("model")
            if not entry.get("cwd") and inherited.get("cwd"):
                entry["cwd"] = inherited.get("cwd")
            if not entry.get("occurred_at") and inherited.get("timestamp"):
                entry["occurred_at"] = inherited.get("timestamp")
        return entry
    except Exception:
        return None


def discover_transcript_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    files: list[Path] = []
    try:
        iterator = root.rglob("*")
    except OSError:
        return []
    for path in iterator:
        try:
            if not path.is_file():
                continue
        except OSError:
            continue
        if any(part in _SKIP_PARTS for part in path.parts):
            continue
        if path.name in _SKIP_NAMES or path.name.startswith("."):
            continue
        suffix = path.suffix.lower()
        name = path.name.lower()
        if suffix == ".jsonl":
            files.append(path)
        elif suffix == ".json" and (
            name in _FILE_NAMES or "transcript" in name or name.endswith("usage.json")
        ):
            files.append(path)
    seen: set[Path] = set()
    out: list[Path] = []
    for path in files:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(path)
    return sorted(out)


def default_drop_roots() -> list[Path]:
    """Well-known local dirs — used only when they already exist."""
    from ardoise import paths as paths_mod

    home = paths_mod.home()
    return [
        home / ".cursor" / "cloud-agent-transcripts",
        home / ".cursor" / "agent-data",
        paths_mod.transcripts_dir(),
        home / "agent-data",
    ]


def transcript_roots(
    *,
    extra: list[Path] | None = None,
    config: dict[str, Any] | None = None,
) -> list[Path]:
    """Configurable + env + optional well-known drop folders."""
    found: list[Path] = []

    def _add(raw: Any) -> None:
        if not raw:
            return
        path = Path(str(raw)).expanduser()
        try:
            if path.is_dir():
                found.append(path)
        except OSError:
            return

    for env_name in _ENV_ROOTS:
        _add(os.environ.get(env_name))
    extra_env = os.environ.get("ARDOISE_TRANSCRIPT_PATHS") or ""
    for part in extra_env.split(os.pathsep):
        _add(part.strip())
    transcripts = {}
    if isinstance(config, dict):
        raw = config.get("transcripts")
        if isinstance(raw, dict):
            transcripts = raw
        elif isinstance(raw, list):
            transcripts = {"paths": raw}
    for item in transcripts.get("paths") or []:
        _add(item)
    for item in extra or []:
        _add(item)
    for item in default_drop_roots():
        _add(item)

    seen: set[Path] = set()
    out: list[Path] = []
    for path in found:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(path)
    return out


def named_run_agents(root: Path) -> dict[str, str]:
    """Map bcId / conversation id → already-named agent from sidecars.

    Prompt-only trees still yield this identity map. No usage rows are invented.
    """
    mapping: dict[str, str] = {}
    if not root.exists():
        return mapping
    try:
        iterator = root.rglob("*")
    except OSError:
        return mapping
    for path in iterator:
        try:
            if not path.is_file() or path.name not in _SIDECARS:
                continue
            if any(part in _SKIP_PARTS for part in path.parts):
                continue
            if path.name in _SKIP_NAMES or path.name.startswith("."):
                continue
        except OSError:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            continue
        if not isinstance(data, dict):
            continue
        agent = extract(data).get("agent")
        if not agent:
            continue
        for ident in _run_id_values(data):
            mapping.setdefault(ident, agent)
    return mapping


def load_named_run_agents(
    *,
    extra: list[Path] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Merge sidecar identity maps from configured + well-known transcript roots."""
    mapping: dict[str, str] = {}
    for root in transcript_roots(extra=extra, config=config):
        for ident, agent in named_run_agents(root).items():
            mapping.setdefault(ident, agent)
    return mapping


def iter_cloud_agent(root: Path) -> Iterator[tuple[Path, dict[str, Any]]]:
    for path in discover_transcript_files(root):
        inherited = sidecar_meta(path)
        for obj in iter_transcript_objects(path):
            entry = parse_line(obj, inherited=inherited)
            if entry:
                yield path, entry
