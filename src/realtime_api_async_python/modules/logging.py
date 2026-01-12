import json
import hashlib
import os
from typing import Any, Dict, Iterable, Optional
import logging
import sys
from rich.logging import RichHandler
from rich.console import Console
from rich.text import Text

console = Console()

def setup_logging():
    logger = logging.getLogger("realtime_api")
    logger.setLevel(logging.INFO)

    if not any(isinstance(h, RichHandler) for h in logger.handlers):
        handler = RichHandler(rich_tracebacks=True, console=console)
        formatter = logging.Formatter("%(message)s", datefmt="[%X]")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.propagate = False
    return logger

logger = setup_logging()

# Function to log WebSocket events
def log_ws_event(direction, event):
    event_type = event.get("type", "Unknown")
    # Hard filter: these are extremely high frequency and can contribute to underruns.
    spammy = {
        "response.output_audio.delta",
        "response.output_audio_transcript.delta",
        "response.function_call_arguments.delta",
    }

    #    "response.text.delta",

    if event_type in spammy:
        return

    event_emojis = {
        "session.update": "🛠️",
        "session.created": "🔌",
        "session.updated": "🔄",
        "input_audio_buffer.append": "🎤",
        "input_audio_buffer.commit": "✅",
        "input_audio_buffer.speech_started": "🗣️",
        "input_audio_buffer.speech_stopped": "🤫",
        "input_audio_buffer.cleared": "🧹",
        "input_audio_buffer.committed": "📨",
        "conversation.item.create": "📝",
        "conversation.item.added": "📥",
        "conversation.item.done": "📝",
        "response.create": "➡️",
        "response.created": "📝",
        "response.content_part.added": "➕",
        "response.content_part.done": "✅",
        "response.output_item.added": "➕",
        "response.output_item.done": "✅",
        "response.output_audio_transcript.delta": "✍️",
        "response.output_audio_transcript.done": "📝",
        "response.output_audio.delta": "🔊",
        "response.output_audio.done": "🔇",
        "response.done": "✔️ ",
        "response.cancel": "⛔",
        "response.function_call_arguments.delta": "📥",
        "response.function_call_arguments.done": "📥",
        "rate_limits.updated": "⏳",
        "error": "❌",
        "conversation.item.input_audio_transcription.completed": "📝",
        "conversation.item.input_audio_transcription.failed": "⚠️",
    }
    emoji = event_emojis.get(event_type, "❓")
    icon = "⬆️ - Out" if direction == "Outgoing" else "⬇️ - In"
    style = "bold cyan" if direction == "Outgoing" else "bold green"
    logger.info(Text(f"{emoji} {icon} {event_type}", style=style))

def log_tool_call(function_name, args, result):
    logger.info(Text(f"🛠️ Calling function: {function_name} with args: {args}", style="bold magenta"))
    logger.info(Text(f"🛠️ Function call result: {result}", style="bold yellow"))

def log_error(message):
    logger.error(Text(message, style="bold red"))

def log_info(message, style="bold white"):
    logger.info(Text(message, style=style))

def log_warning(message):
    logger.warning(Text(message, style="bold yellow"))

# ---------------------------
# Config knobs (tweak freely)
# ---------------------------
MAX_STR           = 38     # cap long strings (instructions, etc.)
MAX_LIST          = 60     # cap list lengths
TOOL_NAME_CAP     = 35     # show first N tool names in summary
REDACT            = True   # if True, redact IDs
REDACT_KEYS       = {"event_id", "id", "session_id"}  # applied during normalization
NO_TRUNCATE_KEYS  = {"instructions"}

# Keys you usually don't need to see every run (set to () to disable)
DROP_SESSION_KEYS = (
    "tracing",
    "prompt",
    "include",
)

# Enable full payload dumps when debugging
#
# To enable payload dumps:
#     export THEO_LOG_SESSION_FULL=1
#
DEBUG_FULL_PAYLOAD = bool(int(os.getenv("THEO_LOG_SESSION_FULL", "0")))

# Markers for grep/AI parsing
MARK_SUMMARY = "--- SESSION_UPDATED_SUMMARY ---"
MARK_PAYLOAD = "--- SESSION_UPDATED_PAYLOAD ---"


# ---------------------------
# Helpers
# ---------------------------
KEEP_SESSION_KEYS = {
    "model",
    "output_modalities",
    "tool_choice",
    "max_output_tokens",
    "truncation",
    "audio",
    "tools",
    "instructions",
}

def _keep_only(d: Dict[str, Any], keys: Iterable[str]) -> Dict[str, Any]:
    return {k: d[k] for k in keys if k in d}


def _truncate_str(s: str, max_len: int = MAX_STR) -> str:
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def _first_line(s: str, max_len: int = 160) -> str:
    if not s:
        return ""
    line = s.strip().splitlines()[0]
    return _truncate_str(line, max_len)


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _shorten_list(lst: list, max_items: int = MAX_LIST) -> list:
    if len(lst) <= max_items:
        return lst
    return lst[:max_items] + [f"… ({len(lst) - max_items} more)"]


def _normalize_for_log(obj: Any, *, _key: Optional[str] = None) -> Any:
    """
    Log-friendly normalization:
      - truncate long strings (except for NO_TRUNCATE_KEYS)
      - shorten long lists
      - stable dict ordering
      - optional redaction
    """
    if isinstance(obj, str):
        if _key in NO_TRUNCATE_KEYS:
            return obj
        return _truncate_str(obj)

    if isinstance(obj, list):
        return [_normalize_for_log(x) for x in _shorten_list(obj)]

    if isinstance(obj, dict):
        out = {}
        for k in sorted(obj.keys(), key=str):
            v = obj[k]
            if REDACT and k in REDACT_KEYS and isinstance(v, str):
                out[k] = "<redacted>"
            else:
                out[k] = _normalize_for_log(v, _key=k)
        return out

    return obj


def _compact_tools(tools: Any) -> list:
    """
    Convert verbose tool schemas into a compact list:
      [{name,type,required,params}]
    """
    if not isinstance(tools, list):
        return []
    compact = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        params = ((t.get("parameters") or {}).get("properties") or {})
        required = (t.get("parameters") or {}).get("required") or []
        compact.append({
            "name": t.get("name"),
            "type": t.get("type"),
            "required": required,
            "params": sorted(params.keys()),
        })
    return compact


def _extract_summary(event: Dict[str, Any]) -> Dict[str, Any]:
    sess = (event or {}).get("session") or {}
    audio = sess.get("audio") or {}

    in_cfg = audio.get("input") or {}
    out_cfg = audio.get("output") or {}

    in_fmt = in_cfg.get("format") or {}
    out_fmt = out_cfg.get("format") or {}

    turn = (in_cfg.get("turn_detection") or {})
    tools = sess.get("tools") or []

    instructions = sess.get("instructions") or ""
    instr_digest = {
        "len": len(instructions),
        "sha256": _sha256(instructions)[:12],  # short hash for quick comparisons
        "preview": _first_line(instructions),
    }

    tool_names = []
    for t in tools:
        if isinstance(t, dict) and t.get("name"):
            tool_names.append(t["name"])

    summary = {
        "type": event.get("type"),
        "event_id": event.get("event_id"),
        "session": {
            "id": sess.get("id"),
            "model": sess.get("model"),
            "output_modalities": sess.get("output_modalities"),
            "tool_choice": sess.get("tool_choice"),
            "max_output_tokens": sess.get("max_output_tokens"),
            "truncation": sess.get("truncation"),
            "expires_at": sess.get("expires_at"),
        },
        "audio": {
            "voice": out_cfg.get("voice"),
            "speed": out_cfg.get("speed"),
            "in": f'{in_fmt.get("type")}@{in_fmt.get("rate")}',
            "out": f'{out_fmt.get("type")}@{out_fmt.get("rate")}',
            "vad": {
                "type": turn.get("type"),
                "threshold": turn.get("threshold"),
                "prefix_padding_ms": turn.get("prefix_padding_ms"),
                "silence_duration_ms": turn.get("silence_duration_ms"),
                "idle_timeout_ms": turn.get("idle_timeout_ms"),
                "create_response": turn.get("create_response"),
                "interrupt_response": turn.get("interrupt_response"),
            },
        },
        "tools": {
            "count": len(tools),
            "names": tool_names[:TOOL_NAME_CAP] + (["…"] if len(tool_names) > TOOL_NAME_CAP else []),
        },
        "instructions_digest": instr_digest,
    }

    if REDACT:
        if summary.get("event_id"):
            summary["event_id"] = "<redacted>"
        if summary["session"].get("id"):
            summary["session"]["id"] = "<redacted>"

    return summary


def _prune_session(sess: Dict[str, Any]) -> Dict[str, Any]:
    if not DROP_SESSION_KEYS:
        return dict(sess)
    pruned = dict(sess)          # keep everything
    for k in DROP_SESSION_KEYS:
        pruned.pop(k, None)
    return pruned


def _prune_nones(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _prune_nones(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_prune_nones(x) for x in obj]
    return obj


def _headline(summary: Dict[str, Any]) -> str:
    s = summary.get("session") or {}
    a = summary.get("audio") or {}
    vad = (a.get("vad") or {})
    instr = (summary.get("instructions_digest") or {})
    tools = (summary.get("tools") or {})
    return (
        "SESSION_UPDATED | "
        f"model={s.get('model')} | "
        f"voice={a.get('voice')} | "
        f"vad={vad.get('type')}(th={vad.get('threshold')},pre={vad.get('prefix_padding_ms')},sil={vad.get('silence_duration_ms')}) | "
        f"tools={tools.get('count')} | "
        f"instr={instr.get('sha256')} ({instr.get('len')})"
    )


def log_session_updated(event: Dict[str, Any], *, full_payload: Optional[bool] = None) -> None:
    """
    Print a summary always, and optionally a compact full payload.
    full_payload:
      - None: use env var THEO_LOG_SESSION_FULL (0/1)
      - True/False: force
    """
    if full_payload is None:
        full_payload = DEBUG_FULL_PAYLOAD

    # SUMMARY
    print(MARK_SUMMARY)
    summary = _extract_summary(event)
    print(_headline(summary))
    print(json.dumps(_normalize_for_log(summary), indent=2, ensure_ascii=False))

    if not full_payload:
        return

    # PAYLOAD (compact & pruned)
    print(MARK_PAYLOAD)
    event2 = dict(event)
    event2 = _prune_nones(event2)

    sess = dict((event2.get("session") or {}))
    sess = _prune_session(sess)
    sess = _keep_only(sess, KEEP_SESSION_KEYS)

    # Replace massive tool schemas with compact versions
    sess["tools"] = _compact_tools(sess.get("tools"))

    # Optional: keep full instructions but capped by MAX_STR via normalization
    # If you *never* want full instructions in payload, uncomment:
    # sess["instructions"] = "<omitted>"

    event2["session"] = sess
    print(json.dumps(_normalize_for_log(event2), indent=2, ensure_ascii=False))

