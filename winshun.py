# Minimal, dependency-free Win顺 once-plugin SDK adapter.
# API-compatible subset of the official Python SDK used by this plugin.
# Replace this file with the SDK copied from your Win顺-generated template if preferred.
import json
import os
import sys


def _env(name, default=""):
    return os.environ.get(name, default)


def debug(text):
    """A line to stderr: plugins.log and, in developer mode, the log pane."""
    sys.stderr.write(str(text) + "\n")
    sys.stderr.flush()


class Query:
    def __init__(self, text="", raw="", command="", trigger="keyword", keyword="", match=None):
        self.text = text
        self.raw = raw
        self.command = command
        self.trigger = trigger
        self.keyword = keyword
        self.match = list(match or [])


def query():
    try:
        groups = json.loads(_env("WS_MATCH", "[]") or "[]")
        if not isinstance(groups, list):
            groups = []
    except (ValueError, TypeError):
        groups = []
    return Query(
        text=_env("WS_QUERY"), raw=_env("WS_TEXT"), command=_env("WS_COMMAND"),
        trigger=_env("WS_TRIGGER", "keyword"), keyword=_env("WS_KEYWORD"), match=groups,
    )


def settings():
    try:
        value = json.loads(_env("WS_SETTINGS", "{}") or "{}")
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def is_action():
    return bool(_env("WS_ACTION"))


def action_request():
    try:
        item_value = json.loads(_env("WS_ITEM", "{}") or "{}")
        if not isinstance(item_value, dict):
            item_value = {}
    except (ValueError, TypeError):
        item_value = {}
    return {
        "action": _env("WS_ACTION", "default"),
        "item": item_value,
        "command": _env("WS_COMMAND"),
        "text": _env("WS_QUERY"),
    }


def item(id, title, subtitle=None, icon=None, score=None, copy=None, path=None, url=None,
         preview=None, data=None, actions=None, valid=True, **more):
    row = {"id": str(id), "title": str(title)}
    if subtitle:
        row["subtitle"] = str(subtitle)
    if icon:
        row["icon"] = icon
    if score is not None:
        row["score"] = int(score)
    if copy is not None:
        row["copy"] = str(copy)
    if path:
        row["open"] = {"path": str(path)}
    elif url:
        row["open"] = {"url": str(url)}
    if preview:
        row["preview"] = {"text": str(preview)}
    if data is not None:
        row["data"] = data
    if actions:
        row["actions"] = actions
    if not valid:
        row["valid"] = False
    row.update(more)
    return row


def action(id, title, key="Enter"):
    return {"id": id, "title": title, "key": key}


def open_path(path):
    return {"type": "open", "path": str(path)}


def notify(text):
    return {"type": "notify", "text": str(text)}


def keep():
    return {"type": "keep"}


def replace(items):
    return {"type": "replace", "items": list(items)}


def set_query(text):
    return {"type": "setQuery", "text": str(text)}


def _write(payload):
    line = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    sys.stdout.write(line)
    sys.stdout.flush()


def reply(items, rerun=0, cache=0):
    result = {"items": list(items)}
    if rerun:
        result["rerun"] = rerun
    if cache:
        result["cache"] = cache
    _write(result)


def effects(*effect_list):
    _write({"effects": list(effect_list)})
