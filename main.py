# -*- coding: utf-8 -*-
"""Obsidian Quick Note Center for Win顺. Python 3, standard library only."""
from __future__ import annotations

import hashlib
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import winshun

PLUGIN_NAME = "Obsidian 快速记录中心"
DEFAULTS = {
    "default_vault": "1",
    "notes_folder": "Notes",
    "daily_folder": "Daily",
    "inbox_file": "Inbox/收集箱.md",
    "todo_file": "Tasks.md",
    "templates_folder": "Templates",
    "detect_code": True,
    "add_source_time": True,
    "open_after_save": True,
}
SKIP_DIRS = {".obsidian", ".git", ".trash", "node_modules", ".venv", "venv"}
MAX_TITLE_FILES = 12000
MAX_DUP_FILES = 600
MAX_DUP_FILE_BYTES = 192 * 1024


class PluginError(Exception):
    pass


def now_local() -> datetime:
    return datetime.now().astimezone()


def merged_settings(raw: Optional[dict] = None) -> dict:
    result = dict(DEFAULTS)
    if isinstance(raw, dict):
        result.update(raw)
    return result


def configured_vaults(settings: dict) -> List[Tuple[int, Path]]:
    vaults = []
    seen = set()
    for index in (1, 2, 3):
        raw = str(settings.get(f"vault_{index}", "") or "").strip().strip('"')
        if not raw:
            continue
        path = Path(os.path.expandvars(os.path.expanduser(raw))).resolve()
        key = os.path.normcase(str(path))
        if key in seen:
            continue
        seen.add(key)
        if path.exists() and path.is_dir():
            vaults.append((index, path))
    return vaults


def selected_vaults(settings: dict, selector: Optional[int] = None) -> List[Tuple[int, Path]]:
    all_vaults = configured_vaults(settings)
    if selector is not None:
        return [entry for entry in all_vaults if entry[0] == selector]
    return all_vaults


def choose_default_vault(vaults: Sequence[Tuple[int, Path]], settings: dict) -> Optional[Tuple[int, Path]]:
    try:
        preferred = int(settings.get("default_vault", "1"))
    except (TypeError, ValueError):
        preferred = 1
    for entry in vaults:
        if entry[0] == preferred:
            return entry
    return vaults[0] if vaults else None


def safe_relative_path(raw: str) -> Path:
    """Reject absolute paths and traversal in user-configurable vault-relative paths."""
    text = str(raw or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        raise PluginError(f"路径必须是 Vault 内的相对路径：{raw}")
    parts = [part for part in text.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise PluginError(f"不允许空路径或 .. 路径：{raw}")
    if any("\x00" in part or any(ch in part for ch in '<>:"|?*') for part in parts):
        raise PluginError("路径包含 Windows 不允许的字符")
    return Path(*parts)


def vault_path(vault: Path, relative: str, *, must_exist: bool = False) -> Path:
    rel = safe_relative_path(relative)
    target = (vault / rel).resolve(strict=must_exist)
    try:
        target.relative_to(vault.resolve())
    except ValueError:
        raise PluginError("目标路径超出 Vault，已阻止写入")
    return target


def display_vault_name(path: Path, index: int) -> str:
    return f"Vault {index} · {path.name or path}"


def stable_id(*parts: str) -> str:
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:16]


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\ufeff", "")).strip().casefold()


def safe_filename(title: str, fallback: str) -> str:
    name = str(title or "").strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    name = name[:90].rstrip(" .")
    if not name:
        name = fallback
    # Device names are reserved with or without an extension: con.txt, COM1.md.
    stem = name.split(".", 1)[0].upper()
    if stem in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(r"COM[1-9]|LPT[1-9]", stem):
        name = f"_{name}"
    return name


def detect_code_language(text: str) -> Optional[str]:
    stripped = text.strip()
    if not stripped or "```" in stripped or "~~~" in stripped:
        return None
    lines = [line for line in stripped.splitlines() if line.strip()]
    joined = "\n".join(lines)
    if len(lines) < 1:
        return None

    patterns = [
        ("python", [r"(?m)^\s*(?:def|class)\s+\w+.*:", r"(?m)^\s*(?:from\s+\S+\s+import|import\s+\S+)", r"\bprint\s*\(", r"\bself\."]),
        ("typescript", [r"\binterface\s+\w+", r"\btype\s+\w+\s*=", r"\b(const|let)\s+\w+\s*[:=]", r"\bimport\s+\{[^}]+\}\s+from", r"\)\s*:\s*(?:void|string|number|Promise)"]),
        ("javascript", [r"\b(const|let|var)\s+\w+\s*=", r"\bfunction\s+\w+\s*\(", r"=>", r"console\.\w+\s*\(", r"\bexport\s+(?:default|const|function)"]),
        ("java", [r"\bpublic\s+class\s+\w+", r"\bpublic\s+static\s+void\s+main", r"System\.out\.print", r"@Override", r"\bimport\s+java\."]),
        ("cpp", [r"#include\s*[<\"]", r"\bint\s+main\s*\(", r"std::", r"std::cout", r"\bclass\s+\w+\s*\{"]),
        ("sql", [r"(?i)\bselect\b.+\bfrom\b", r"(?i)\b(insert\s+into|create\s+table|update\s+\w+\s+set)\b", r"(?i)\bwhere\b"]),
        ("bash", [r"^#!.*(?:bash|sh)", r"(?m)^\s*(?:git|npm|pnpm|yarn|docker|adb|curl|chmod|sudo)\s+", r"\$\s+[\w./-]+"]),
        ("json", [r"^\s*[\[{]\s*\n?\s*[\"']?\w+[\"']?\s*:", r"(?m)^\s*\"[\w-]+\"\s*:"]),
    ]
    scores = []
    for language, regs in patterns:
        score = sum(1 for pattern in regs if re.search(pattern, joined))
        if score:
            scores.append((score, language))
    if not scores:
        return None
    scores.sort(reverse=True)
    score, language = scores[0]
    # A single highly distinctive line is enough; ambiguous prose is not wrapped.
    if score >= 2:
        return language
    distinctive = {
        "python": [r"(?m)^\s*def\s+\w+.*:", r"(?m)^\s*class\s+\w+.*:"],
        "java": [r"\bpublic\s+class\s+\w+", r"\bpublic\s+static\s+void\s+main"],
        "cpp": [r"#include\s*[<\"]", r"\bint\s+main\s*\("],
        "sql": [r"(?i)\bselect\b.+\bfrom\b"],
        "bash": [r"^#!.*(?:bash|sh)"],
    }
    if any(re.search(p, joined) for p in distinctive.get(language, [])):
        return language
    return None


def maybe_fence_code(text: str, enabled: bool) -> str:
    value = text.strip()
    if not enabled:
        return value
    language = detect_code_language(value)
    if not language:
        return value
    return f"```{language}\n{value}\n```"


def markdown_escape_yaml(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def note_block(text: str, stamp: datetime, settings: dict) -> str:
    body = maybe_fence_code(text, bool(settings.get("detect_code", True)))
    if settings.get("add_source_time", True):
        return (
            f"\n\n## {stamp:%Y-%m-%d %H:%M}\n\n"
            f"{body}\n\n"
            f"<sub>记录时间：{stamp:%Y-%m-%d %H:%M:%S} · 来源：Win顺</sub>\n"
        )
    return f"\n\n## {stamp:%Y-%m-%d %H:%M}\n\n{body}\n"


def initial_inbox_content(stamp: datetime) -> str:
    return f"---\ncreated: {stamp:%Y-%m-%d}\nsource: WinShun\n---\n\n# 收集箱\n"


def initial_todo_content() -> str:
    return "# 待办事项\n\n"


def ensure_frontmatter(content: str, stamp: datetime, title: Optional[str] = None) -> str:
    """Ensure date/time/source metadata exists without duplicating template keys."""
    body = content.lstrip("\ufeff")
    header = ""
    rest = body
    if body.startswith("---\n") or body.startswith("---\r\n"):
        match = re.search(r"(?m)^---\s*$", body[4:])
        if match:
            end = 4 + match.start()
            header = body[4:end]
            rest = body[4 + match.end():].lstrip("\r\n")
    values = {
        "date": stamp.strftime("%Y-%m-%d"),
        "created": stamp.strftime("%Y-%m-%d %H:%M:%S"),
        "time": stamp.strftime("%H:%M:%S"),
        "source": "Win顺",
    }
    if title is not None:
        values["title"] = markdown_escape_yaml(title)
    existing_keys = set(re.findall(r"(?m)^([A-Za-z_][A-Za-z0-9_-]*):", header))
    additions = []
    for key, value in values.items():
        if key not in existing_keys:
            additions.append(f'{key}: "{value}"')
    merged_header = header.rstrip()
    if additions:
        merged_header = (merged_header + "\n" if merged_header else "") + "\n".join(additions)
    return f"---\n{merged_header}\n---\n\n{rest}" if rest else f"---\n{merged_header}\n---\n"


def initial_daily_content(stamp: datetime, template: Optional[str] = None) -> str:
    if template:
        return ensure_frontmatter(substitute_template(template, f"{stamp:%Y-%m-%d}", stamp), stamp, f"{stamp:%Y-%m-%d}")
    return (
        f"---\ndate: {stamp:%Y-%m-%d}\ncreated: {stamp:%Y-%m-%d %H:%M:%S}\ntime: {stamp:%H:%M:%S}\nsource: Win顺\n---\n\n"
        f"# {stamp:%Y-%m-%d}\n\n## 今日记录\n\n## 待办\n\n- [ ] \n\n## 回顾\n"
    )


def substitute_template(content: str, title: str, stamp: datetime) -> str:
    replacements = {
        "{{title}}": title,
        "{{date}}": stamp.strftime("%Y-%m-%d"),
        "{{time}}": stamp.strftime("%H:%M:%S"),
        "{{datetime}}": stamp.strftime("%Y-%m-%d %H:%M:%S"),
        "{{source}}": "Win顺",
    }
    for key, value in replacements.items():
        content = content.replace(key, value)
    return content


def iter_markdown(vault: Path, max_files: int = MAX_TITLE_FILES) -> Iterable[Path]:
    count = 0
    for root, dirs, files in os.walk(vault):
        dirs[:] = [d for d in dirs if d.casefold() not in SKIP_DIRS and not d.startswith(".")]
        for filename in files:
            if not filename.lower().endswith(".md"):
                continue
            path = Path(root) / filename
            if path.is_symlink():
                continue
            yield path
            count += 1
            if count >= max_files:
                return


def search_titles(vaults: Sequence[Tuple[int, Path]], keywords: str, limit: int = 30) -> List[dict]:
    words = [w.casefold() for w in re.findall(r"[^\s]+", keywords.strip())]
    if not words:
        return []
    matches = []
    seen = set()
    for index, vault in vaults:
        for path in iter_markdown(vault):
            title = path.stem.casefold()
            if not all(word in title for word in words):
                continue
            resolved = path.resolve()
            try:
                resolved.relative_to(vault.resolve())
            except ValueError:
                continue
            norm = os.path.normcase(str(resolved))
            if norm in seen:
                continue
            seen.add(norm)
            relative = resolved.relative_to(vault.resolve()).as_posix()
            matches.append({
                "id": stable_id("search", str(resolved)),
                "title": path.stem,
                "subtitle": f"{display_vault_name(vault, index)} · {relative}",
                "open": {"path": str(resolved)},
                "copy": str(resolved),
                "score": 90 - min(len(str(path)), 80),
            })
            if len(matches) >= limit:
                return matches
    return matches


def find_exact_duplicates(vaults: Sequence[Tuple[int, Path]], content: str) -> List[Tuple[Path, str]]:
    needle = normalize_text(content)
    if len(needle) < 12:
        return []
    found = []
    checked = 0
    for _index, vault in vaults:
        vault_root = vault.resolve()
        for path in iter_markdown(vault, max_files=MAX_DUP_FILES):
            try:
                if path.is_symlink() or path.stat().st_size > MAX_DUP_FILE_BYTES:
                    continue
                # A junction inside the vault can point outside; never read it.
                try:
                    path.resolve().relative_to(vault_root)
                except ValueError:
                    continue
                existing = path.read_text(encoding="utf-8-sig", errors="ignore")
            except (OSError, UnicodeError, RuntimeError):
                continue
            checked += 1
            if needle in normalize_text(existing):
                found.append((path.resolve(), path.stem))
                if len(found) >= 5:
                    return found
            if checked >= MAX_DUP_FILES:
                return found
    return found


def make_error_item(message: str) -> dict:
    return winshun.item("error-" + stable_id(message), message, "请检查插件设置或输入", icon="glyph:U+E783", valid=False)


def make_action_item(item_id: str, title: str, subtitle: str, preview: str, data: dict,
                     action_id: str = "save", action_title: str = "确认并保存") -> dict:
    return winshun.item(
        item_id, title, subtitle, icon="glyph:U+E8A5", preview=preview,
        copy=preview, data=data,
        actions=[winshun.action(action_id, action_title, "Enter")],
    )


def help_items() -> List[dict]:
    return [
        winshun.item("help-note", "note 内容", "记录到收集箱；Enter 前可查看预览", copy="note "),
        winshun.item("help-todo", "todo 内容", "添加待办事项", copy="todo "),
        winshun.item("help-daily", "daily", "打开或创建今日日记", copy="daily"),
        winshun.item("help-inbox", "inbox", "打开或创建收集箱", copy="inbox"),
        winshun.item("help-template", "note --template", "从 Templates 目录选择模板", copy="note --template"),
        winshun.item("help-search", "note 关键词", "搜索所有已配置 Vault 的 Markdown 标题", copy="note "),
    ]


def parse_vault_selector(text: str) -> Tuple[Optional[int], str]:
    match = re.match(r"^\s*--vault\s+([123])(?:\s+|$)", text)
    if not match:
        return None, text.strip()
    return int(match.group(1)), text[match.end():].strip()


def list_templates(vault: Path, index: int, settings: dict, filter_text: str = "") -> List[dict]:
    folder = str(settings.get("templates_folder", "Templates"))
    template_root = vault_path(vault, folder)
    if not template_root.exists() or not template_root.is_dir():
        return []
    rows = []
    needle = filter_text.casefold().strip()
    for path in iter_markdown(template_root, max_files=300):
        if needle and needle not in path.stem.casefold():
            continue
        try:
            if path.is_symlink():
                continue
            path.resolve().relative_to(vault.resolve())
            body = path.read_text(encoding="utf-8-sig", errors="replace")
        except (OSError, ValueError):
            continue
        rel = path.resolve().relative_to(vault.resolve()).as_posix()
        rows.append(winshun.item(
            "tpl-" + stable_id(str(path.resolve())), path.stem,
            f"{display_vault_name(vault, index)} · {rel}",
            icon="glyph:U+E8A5", preview=body[:12000], copy=body,
            data={"kind": "template", "vault_index": index, "template_rel": rel},
            actions=[winshun.action("use-template", "使用此模板创建笔记", "Enter")],
        ))
    return rows[:50]


def query_note(q, settings: dict) -> List[dict]:
    text = q.text.strip()
    vault_selector, text = parse_vault_selector(text)
    vaults = selected_vaults(settings, vault_selector)
    if not vaults:
        if configured_vaults(settings):
            return [make_error_item(f"没有找到 Vault {vault_selector}，请在插件设置中检查路径。")]
        return [
            make_error_item("尚未配置 Obsidian Vault。请在 Win顺 → 设置 → 插件 → Obsidian 快速记录中心中设置 Vault 1。"),
            winshun.item("settings", "打开插件设置", "配置 Vault 路径", url="winshun:settings"),
        ]

    if text in ("--help", "-h", "--help"):
        return help_items()

    if text.startswith("--template"):
        rest = text[len("--template"):].strip()
        custom_title = None
        title_match = re.search(r"\s+--title\s+(.+)$", rest)
        if title_match:
            custom_title = title_match.group(1).strip().strip('"')
            rest = rest[:title_match.start()].strip()
        template_filter = rest.strip('"')
        selected = selected_vaults(settings, vault_selector)
        target_vault = choose_default_vault(selected, settings)
        if target_vault is None:
            return [make_error_item("没有配置可用的 Vault。")]
        index, vault = target_vault
        templates = list_templates(vault, index, settings, template_filter)
        if not templates:
            return [make_error_item(f"模板目录中没有匹配的 Markdown 模板：{settings.get('templates_folder', 'Templates')}。")]
        if custom_title:
            for row in templates:
                row["data"]["custom_title"] = custom_title
                row["subtitle"] += f" · 新文件名：{custom_title}.md"
        return templates

    if text.startswith("--search "):
        search_term = text[len("--search "):].strip()
        if not search_term:
            return [make_error_item("请在 --search 后输入标题关键词。")]
        return [winshun.item(**row) for row in search_titles(vaults, search_term, q.limit if hasattr(q, "limit") else 30)] or [
            make_error_item(f"没有找到标题包含“{search_term}”的笔记。")
        ]

    if not text:
        return help_items()

    stamp = now_local()
    inbox_rel = str(settings.get("inbox_file", DEFAULTS["inbox_file"]))
    search_rows = search_titles(vaults, text, min(25, getattr(q, "limit", 200)))
    result = []

    for index, vault in vaults:
        try:
            target = vault_path(vault, inbox_rel)
            body = maybe_fence_code(text, bool(settings.get("detect_code", True)))
            sample = f"## {stamp:%Y-%m-%d %H:%M}\n\n{body}\n"
            payload = {
                "kind": "append-note", "vault_index": index,
                "relative_path": inbox_rel, "text": text,
                "timestamp": stamp.isoformat(timespec="seconds"),
            }
            vault_label = display_vault_name(vault, index)
            result.append(make_action_item(
                "note-save-" + stable_id(str(target), text),
                f"记录到收集箱 · {vault.name}",
                f"{vault_label} · {inbox_rel} · Enter 保存",
                sample,
                payload,
                "save-note", "预览后保存",
            ))
        except PluginError as exc:
            result.append(make_error_item(str(exc)))

    result.extend([winshun.item(**row) for row in search_rows])
    if not search_rows:
        result.append(winshun.item("search-empty", "没有匹配的笔记标题", "仍可按上方结果把内容记录到收集箱", valid=False))
    return result[:min(50, max(10, getattr(q, "limit", 200)))]


def query_todo(q, settings: dict) -> List[dict]:
    text = q.text.strip()
    vault_selector, text = parse_vault_selector(text)
    vaults = selected_vaults(settings, vault_selector)
    if not vaults:
        return [make_error_item("请先在插件设置中配置 Vault 1。")]
    if not text:
        return [winshun.item("todo-hint", "todo 学习 Three.js", "输入待办内容后，预览并按 Enter 追加", copy="todo ")]
    stamp = now_local()
    relative = str(settings.get("todo_file", DEFAULTS["todo_file"]))
    rows = []
    for index, vault in vaults:
        try:
            target = vault_path(vault, relative)
            preview_task = re.sub(r"\s+", " ", text).strip()
            line = f"- [ ] [{stamp:%Y-%m-%d %H:%M}] {preview_task} <!-- source: Win顺 -->"
            data = {"kind": "append-todo", "vault_index": index, "relative_path": relative,
                    "text": text, "timestamp": stamp.isoformat(timespec="seconds")}
            rows.append(make_action_item(
                "todo-" + stable_id(str(target), text), f"添加待办 · {vault.name}",
                f"{display_vault_name(vault, index)} · {relative} · Enter 添加",
                line, data, "save-todo", "预览后添加待办",
            ))
        except PluginError as exc:
            rows.append(make_error_item(str(exc)))
    return rows


def query_open_file(command: str, settings: dict) -> List[dict]:
    vaults = selected_vaults(settings)
    target_vault = choose_default_vault(vaults, settings)
    if not target_vault:
        return [make_error_item("请先在插件设置中配置一个有效的 Vault 文件夹。")]
    index, vault = target_vault
    stamp = now_local()
    if command == "daily":
        rel = (Path(str(settings.get("daily_folder", DEFAULTS["daily_folder"]))) / f"{stamp:%Y-%m-%d}.md").as_posix()
        rel = safe_relative_path(rel).as_posix()
        label = "今日日记"
        content = initial_daily_content(stamp, read_template_for_daily(vault, settings, stamp))
    else:
        rel = safe_relative_path(str(settings.get("inbox_file", DEFAULTS["inbox_file"]))).as_posix()
        label = "收集箱"
        content = initial_inbox_content(stamp)
    try:
        target = vault_path(vault, rel)
    except PluginError as exc:
        return [make_error_item(str(exc))]
    if target.exists() and target.is_file():
        return [winshun.item(
            f"open-{command}-{stable_id(str(target))}", f"打开{label}",
            f"{display_vault_name(vault, index)} · {rel}",
            path=str(target), copy=str(target), icon="ext:md",
        )]
    payload = {"kind": "create-open", "vault_index": index, "relative_path": rel,
               "content": content, "label": label}
    return [make_action_item(
        f"create-{command}-{stable_id(str(target))}", f"创建并打开{label}",
        f"文件尚不存在 · {display_vault_name(vault, index)} · {rel}",
        content, payload, "create-open", "确认创建并打开",
    )]


def query(q, settings: dict) -> List[dict]:
    command = q.command
    if command == "note":
        return query_note(q, settings)
    if command == "todo":
        return query_todo(q, settings)
    if command in ("daily", "inbox"):
        return query_open_file(command, settings)
    return [make_error_item(f"不支持的命令：{command or '(空)'}")]


def read_template_for_daily(vault: Path, settings: dict, stamp: datetime) -> Optional[str]:
    template_root = vault_path(vault, str(settings.get("templates_folder", "Templates")))
    candidates = [template_root / "日记.md", template_root / "Daily.md", template_root / "daily.md"]
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(vault.resolve())
            if resolved.is_file():
                return resolved.read_text(encoding="utf-8-sig", errors="replace")
        except (OSError, ValueError):
            continue
    return None


def ensure_parent(target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)


def append_note(vault: Path, relative: str, text: str, stamp: datetime, settings: dict) -> Path:
    target = vault_path(vault, relative)
    ensure_parent(target)
    block = note_block(text, stamp, settings)
    if not target.exists():
        content = initial_inbox_content(stamp) + block.lstrip("\n")
        with target.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
    else:
        if not target.is_file():
            raise PluginError("收集箱目标不是普通文件")
        if target.stat().st_size > 50 * 1024 * 1024:
            raise PluginError("收集箱文件超过 50 MB，已停止写入")
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(block)
    return target.resolve()


def append_todo(vault: Path, relative: str, text: str, stamp: datetime) -> Path:
    target = vault_path(vault, relative)
    ensure_parent(target)
    task_text = re.sub(r"\s+", " ", text).strip()
    line = f"- [ ] [{stamp:%Y-%m-%d %H:%M}] {task_text} <!-- source: Win顺 -->\n"
    if not target.exists():
        with target.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(initial_todo_content() + line)
    else:
        if not target.is_file():
            raise PluginError("待办目标不是普通文件")
        if target.stat().st_size > 20 * 1024 * 1024:
            raise PluginError("待办文件超过 20 MB，已停止写入")
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
    return target.resolve()


def write_new_file(target: Path, content: str) -> Tuple[Path, bool]:
    """Create the file; on collision return (target, False) and leave it untouched."""
    target = target.resolve(strict=False)
    ensure_parent(target)
    try:
        with target.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
    except FileExistsError:
        return target.resolve(), False
    return target.resolve(), True


def unique_note_path(vault: Path, notes_folder: str, title: str, stamp: datetime) -> Tuple[Path, str]:
    folder = safe_relative_path(notes_folder)
    safe_title = safe_filename(title, f"未命名-{stamp:%Y%m%d-%H%M%S}")
    relative = (folder / f"{safe_title}.md").as_posix()
    target = vault_path(vault, relative)
    if target.exists():
        relative = (folder / f"{safe_title} {stamp:%Y%m%d-%H%M%S}.md").as_posix()
        target = vault_path(vault, relative)
    return target, relative


def duplicate_result_items(duplicates: Sequence[Tuple[Path, str]], payload: dict) -> List[dict]:
    rows = [winshun.item(
        "duplicate-" + stable_id(str(path)), f"可能重复：{title}", str(path),
        path=str(path), copy=str(path), icon="ext:md",
    ) for path, title in duplicates]
    rows.append(winshun.item(
        "force-save-" + stable_id(str(payload.get("relative_path")), str(payload.get("text"))),
        "仍然保存这条记录", "已发现相同内容；确认后仍然写入，不覆盖原笔记",
        preview=str(payload.get("text", "")), copy=str(payload.get("text", "")), data=payload,
        actions=[winshun.action("force-save", "忽略重复并保存", "Enter")],
        icon="glyph:U+E8A5",
    ))
    return rows


def action_result(req: dict, settings: dict) -> None:
    item_data = req.get("item", {})
    data = item_data.get("data", {}) if isinstance(item_data, dict) else {}
    if not isinstance(data, dict):
        raise PluginError("动作数据无效，请重新查询后操作")
    action_id = str(req.get("action", "default"))
    kind = str(data.get("kind", ""))
    vault_index = int(data.get("vault_index", 0) or 0)
    vault_entry = next((entry for entry in configured_vaults(settings) if entry[0] == vault_index), None)
    if not vault_entry:
        raise PluginError("目标 Vault 未配置或目录已不存在")
    _index, vault = vault_entry

    if kind == "append-note":
        text = str(data.get("text", "")).strip()
        if not text:
            raise PluginError("笔记内容不能为空")
        relative = str(data.get("relative_path", settings.get("inbox_file", DEFAULTS["inbox_file"])))
        if action_id != "force-save":
            duplicates = find_exact_duplicates(configured_vaults(settings), text)
            if duplicates:
                winshun.effects(
                    winshun.notify(f"检测到 {len(duplicates)} 条可能重复的笔记。请检查后决定是否仍然保存。"),
                    winshun.replace(duplicate_result_items(duplicates, data)),
                    winshun.keep(),
                )
                return
        stamp = datetime.fromisoformat(str(data.get("timestamp"))) if data.get("timestamp") else now_local()
        target = append_note(vault, relative, text, stamp, settings)
        effects = [winshun.notify(f"已记录到收集箱：{target.name}")]
        if settings.get("open_after_save", True):
            effects.append(winshun.open_path(str(target)))
        winshun.effects(*effects)
        return

    if kind == "append-todo":
        text = str(data.get("text", "")).strip()
        if not text:
            raise PluginError("待办内容不能为空")
        relative = str(data.get("relative_path", settings.get("todo_file", DEFAULTS["todo_file"])))
        if action_id != "force-save":
            target = vault_path(vault, relative)
            if target.exists() and target.is_file():
                if target.stat().st_size > 20 * 1024 * 1024:
                    raise PluginError("待办文件超过 20 MB，已停止重复检查")
                current = normalize_text(target.read_text(encoding="utf-8-sig", errors="replace"))
                if normalize_text(text) in current:
                    duplicate = [(target.resolve(), target.stem)]
                    force_data = dict(data)
                    winshun.effects(
                        winshun.notify("待办文件中似乎已经有相同内容。"),
                        winshun.replace(duplicate_result_items(duplicate, force_data)),
                        winshun.keep(),
                    )
                    return
        stamp = datetime.fromisoformat(str(data.get("timestamp"))) if data.get("timestamp") else now_local()
        target = append_todo(vault, relative, text, stamp)
        effects = [winshun.notify(f"待办已添加：{text[:60]}")]
        if settings.get("open_after_save", True):
            effects.append(winshun.open_path(str(target)))
        winshun.effects(*effects)
        return

    if kind == "create-open":
        relative = str(data.get("relative_path", ""))
        target = vault_path(vault, relative)
        content = str(data.get("content", ""))
        if target.exists():
            if not target.is_file():
                raise PluginError("目标路径存在，但不是普通文件")
            created = False
        else:
            target, created = write_new_file(target, content)
        if created:
            message = f"已准备{data.get('label', '文件')}"
        else:
            message = f"文件已存在，未覆盖，已打开现有文件：{target.name}"
        winshun.effects(winshun.notify(message), winshun.open_path(str(target)))
        return

    if kind == "template":
        template_rel = str(data.get("template_rel", ""))
        template_root = vault_path(vault, str(settings.get("templates_folder", "Templates")))
        template_path = vault_path(vault, template_rel, must_exist=True)
        try:
            template_path.relative_to(template_root.resolve())
        except ValueError:
            raise PluginError("模板文件不在配置的模板目录中")
        if not template_path.is_file() or template_path.suffix.lower() != ".md":
            raise PluginError("模板必须是 Templates 目录中的 Markdown 文件")
        template = template_path.read_text(encoding="utf-8-sig", errors="replace")
        stamp = now_local()
        title = str(data.get("custom_title") or f"{template_path.stem} {stamp:%Y-%m-%d %H-%M}")
        title = safe_filename(title, f"未命名-{stamp:%Y%m%d-%H%M%S}")
        target, relative = unique_note_path(vault, str(settings.get("notes_folder", "Notes")), title, stamp)
        output = ensure_frontmatter(substitute_template(template, title, stamp), stamp, title)
        target, created = write_new_file(target, output)
        if created:
            message = f"已使用模板创建：{target.name}"
        else:
            message = f"文件已存在，未覆盖，已打开现有文件：{target.name}"
        effects = [winshun.notify(message)]
        if settings.get("open_after_save", True):
            effects.append(winshun.open_path(str(target)))
        winshun.effects(*effects)
        return

    raise PluginError(f"不支持的动作：{action_id} / {kind}")


def action_payload(request) -> dict:
    """Accept this plugin's dict and the official SDK's ActionRequest object.

    The official SDK returns an ActionRequest whose action/item/command/text are
    attributes; the bundled adapter returns a plain dict.
    """
    if isinstance(request, dict):
        return request
    return {
        "action": getattr(request, "action", "default"),
        "item": getattr(request, "item", None) or {},
        "command": getattr(request, "command", ""),
        "text": getattr(request, "text", ""),
    }


def dispatch() -> None:
    settings = merged_settings(winshun.settings())
    try:
        if winshun.is_action():
            action_result(action_payload(winshun.action_request()), settings)
        else:
            q = winshun.query()
            rows = query(q, settings)
            winshun.reply(rows)
    except Exception as exc:
        # stdout remains protocol-only; diagnostics go to stderr/plugins.log.
        winshun.debug(f"{PLUGIN_NAME}: {type(exc).__name__}: {exc}")
        if winshun.is_action():
            winshun.effects(winshun.notify(f"操作失败：{exc}"), winshun.keep())
        else:
            winshun.reply([make_error_item(f"操作失败：{exc}")])


if __name__ == "__main__":
    dispatch()
