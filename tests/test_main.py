import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main


class QueryStub:
    def __init__(self, command, text="", limit=200):
        self.command = command
        self.text = text
        self.limit = limit


class OfficialActionRequest:
    """Mirror of the official winshun.py ActionRequest: attributes only, no .get()."""

    def __init__(self, action="default", item=None, command="", text="", trigger="", files=None):
        self.action = action
        self.item = item or {}
        self.command = command
        self.text = text
        self.trigger = trigger
        self.files = list(files or [])


class ObsidianQuickNoteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self.tmp.name) / "Vault"
        self.vault.mkdir()
        (self.vault / "Templates").mkdir()
        self.settings = main.merged_settings({
            "vault_1": str(self.vault),
            "default_vault": "1",
            "open_after_save": False,
        })

    def tearDown(self):
        self.tmp.cleanup()

    def test_code_detection(self):
        code = "const value = 1;\nconsole.log(value);"
        self.assertEqual(main.detect_code_language(code), "javascript")
        self.assertTrue(main.maybe_fence_code(code, True).startswith("```javascript\n"))
        self.assertEqual(main.maybe_fence_code("这是一段普通中文说明。", True), "这是一段普通中文说明。")
        fenced = "```js\nconsole.log(1)\n```"
        self.assertEqual(main.maybe_fence_code(fenced, True), fenced)

    def test_path_traversal_rejected(self):
        with self.assertRaises(main.PluginError):
            main.safe_relative_path("../outside.md")
        with self.assertRaises(main.PluginError):
            main.vault_path(self.vault, "../outside.md")
        with self.assertRaises(main.PluginError):
            main.safe_relative_path("Notes/secret.md:stream")

    def test_append_note_adds_metadata(self):
        stamp = datetime(2026, 11, 10, 21, 30, tzinfo=timezone.utc)
        target = main.append_note(self.vault, "Inbox/收集箱.md", "今天学习 Vue3", stamp, self.settings)
        content = target.read_text(encoding="utf-8")
        self.assertIn("# 收集箱", content)
        self.assertIn("## 2026-11-10 21:30", content)
        self.assertIn("来源：Win顺", content)
        self.assertIn("今天学习 Vue3", content)

    def test_append_todo(self):
        stamp = datetime(2026, 11, 10, 21, 30, tzinfo=timezone.utc)
        target = main.append_todo(self.vault, "Tasks.md", "完成 BufferGeometry", stamp)
        self.assertIn("- [ ] [2026-11-10 21:30] 完成 BufferGeometry", target.read_text(encoding="utf-8"))

    def test_duplicate_content_found(self):
        existing = self.vault / "Notes" / "existing.md"
        existing.parent.mkdir()
        existing.write_text("这是一段需要检测重复内容的完整笔记。", encoding="utf-8")
        result = main.find_exact_duplicates([(1, self.vault)], "这是一段需要检测重复内容的完整笔记。")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], existing.resolve())

    def test_duplicate_check_ignores_paths_outside_the_vault(self):
        outside = Path(self.tmp.name) / "outside" / "leak.md"
        outside.parent.mkdir()
        content = "这是一段需要检测重复内容的完整笔记。"
        outside.write_text(content, encoding="utf-8")

        with mock.patch.object(main, "iter_markdown", return_value=[outside]):
            result = main.find_exact_duplicates([(1, self.vault)], content)

        self.assertEqual(result, [])

    @unittest.skipUnless(os.name == "nt", "目录联接只在 Windows 上测试")
    def test_duplicate_check_skips_directory_junctions(self):
        content = "这是一段需要检测重复内容的完整笔记。"
        outside_dir = Path(self.tmp.name) / "outside"
        outside_dir.mkdir()
        outside_file = outside_dir / "leak.md"
        outside_file.write_text(content, encoding="utf-8")

        link = self.vault / "junction"
        proc = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside_dir)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            self.skipTest("无法创建目录联接：%s" % proc.stderr)
        try:
            inside = self.vault / "Notes" / "dup.md"
            inside.parent.mkdir()
            inside.write_text(content, encoding="utf-8")

            result = main.find_exact_duplicates([(1, self.vault)], content)
            paths = [path for path, _title in result]

            self.assertIn(inside.resolve(), paths)
            self.assertNotIn(outside_file.resolve(), paths)
        finally:
            if link.exists():
                os.rmdir(link)

    def test_safe_filename_blocks_device_names_with_extensions(self):
        self.assertEqual(main.safe_filename("con", "fallback"), "_con")
        self.assertEqual(main.safe_filename("con.txt", "fallback"), "_con.txt")
        self.assertEqual(main.safe_filename("COM1.md", "fallback"), "_COM1.md")
        self.assertEqual(main.safe_filename("NUL.txt", "fallback"), "_NUL.txt")
        self.assertEqual(main.safe_filename("mycon", "fallback"), "mycon")
        self.assertEqual(main.safe_filename("concert", "fallback"), "concert")
        self.assertEqual(main.safe_filename("con2", "fallback"), "con2")
        self.assertEqual(main.safe_filename("", "fallback"), "fallback")

    def test_write_new_file_reports_created_and_keeps_the_old_content(self):
        target = self.vault / "Notes" / "new.md"

        path, created = main.write_new_file(target, "第一版")

        self.assertTrue(created)
        self.assertEqual(path.read_text(encoding="utf-8"), "第一版")

        path, created = main.write_new_file(target, "第二版")

        self.assertFalse(created)
        self.assertEqual(path.read_text(encoding="utf-8"), "第一版")

    def action_effects(self, request):
        output = io.StringIO()
        with redirect_stdout(output):
            main.action_result(request, self.settings)
        return json.loads(output.getvalue())["effects"]

    def create_open_request(self, relative, content="内容", label="今日日记"):
        return {
            "action": "open",
            "item": {"data": {
                "kind": "create-open",
                "vault_index": 1,
                "relative_path": relative,
                "content": content,
                "label": label,
            }},
        }

    def test_create_open_new_file_uses_the_success_message(self):
        effects = self.action_effects(self.create_open_request("Daily/2026-11-10.md"))

        self.assertEqual(effects[0], {"type": "notify", "text": "已准备今日日记"})
        self.assertTrue((self.vault / "Daily" / "2026-11-10.md").exists())

    def test_create_open_existing_file_reports_no_overwrite(self):
        target = self.vault / "Daily" / "2026-11-10.md"
        target.parent.mkdir()
        target.write_text("原来的内容", encoding="utf-8")

        effects = self.action_effects(self.create_open_request("Daily/2026-11-10.md"))

        self.assertIn("已存在，未覆盖", effects[0]["text"])
        self.assertIn("现有文件", effects[0]["text"])
        self.assertEqual(target.read_text(encoding="utf-8"), "原来的内容")

    def test_template_existing_file_reports_no_overwrite(self):
        template = self.vault / "Templates" / "会议纪要.md"
        template.write_text("# {{title}}\n", encoding="utf-8")
        target = self.vault / "Notes" / "fixed.md"
        target.parent.mkdir()
        target.write_text("旧内容", encoding="utf-8")
        request = {
            "action": "use-template",
            "item": {"data": {
                "kind": "template",
                "vault_index": 1,
                "template_rel": "Templates/会议纪要.md",
                "custom_title": "fixed",
            }},
        }

        with mock.patch.object(main, "unique_note_path", return_value=(target, "Notes/fixed.md")):
            effects = self.action_effects(request)

        self.assertIn("已存在，未覆盖", effects[0]["text"])
        self.assertEqual(target.read_text(encoding="utf-8"), "旧内容")

    def test_query_does_not_write(self):
        rows = main.query(QueryStub("note", "一条仅用于查询预览的记录"), self.settings)
        self.assertTrue(any(row.get("data", {}).get("kind") == "append-note" for row in rows))
        self.assertFalse((self.vault / "Inbox" / "收集箱.md").exists())

    def test_daily_query_does_not_create_until_action(self):
        rows = main.query(QueryStub("daily"), self.settings)
        self.assertEqual(rows[0]["data"]["kind"], "create-open")
        self.assertFalse((self.vault / "Daily" / "2026-11-10.md").exists())

    def test_template_creation_safe_filename(self):
        template = self.vault / "Templates" / "会议纪要.md"
        template.write_text("# {{title}}\n\n日期：{{date}}\n来源：{{source}}\n", encoding="utf-8")
        rows = main.list_templates(self.vault, 1, self.settings)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["data"]["kind"], "template")
        self.assertEqual(main.safe_filename('a<>:"/b', "fallback"), "a-----b")


    def test_daily_uses_daily_template_when_created(self):
        daily_template = self.vault / "Templates" / "日记.md"
        daily_template.write_text("# {{title}}\n\n日期：{{date}}\n", encoding="utf-8")
        rows = main.query(QueryStub("daily"), self.settings)
        self.assertIn("日期：", rows[0]["preview"]["text"])
        self.assertIn("{{date}}", daily_template.read_text(encoding="utf-8"))

    def test_template_action_creates_note_and_substitutes_placeholders(self):
        template = self.vault / "Templates" / "会议纪要.md"
        template.write_text("# {{title}}\n\n日期：{{date}}\n来源：{{source}}\n", encoding="utf-8")
        rows = main.list_templates(self.vault, 1, self.settings)
        row = rows[0]
        request = {"action": "use-template", "item": {"data": row["data"]}}
        # Freeze the clock only for content assertions; file name includes a generated local timestamp.
        from contextlib import redirect_stdout
        import io
        output = io.StringIO()
        with redirect_stdout(output):
            main.action_result(request, self.settings)
        self.assertIn("effects", json.loads(output.getvalue()))
        notes = list((self.vault / "Notes").glob("*.md"))
        self.assertEqual(len(notes), 1)
        content = notes[0].read_text(encoding="utf-8")
        self.assertNotIn("{{title}}", content)
        self.assertIn('source: "Win顺"', content)
        self.assertIn("created:", content)


    def test_empty_and_invalid_queries_have_clear_results(self):
        empty_rows = main.query(QueryStub("note", ""), self.settings)
        self.assertTrue(any(row["title"] == "note 内容" for row in empty_rows))
        invalid_rows = main.query(QueryStub("not-a-command", "x"), self.settings)
        self.assertTrue(invalid_rows[0]["title"].startswith("不支持的命令"))

    def test_missing_vault_has_setup_hint(self):
        no_vault_settings = main.merged_settings({"vault_1": "", "vault_2": "", "vault_3": ""})
        rows = main.query(QueryStub("inbox"), no_vault_settings)
        self.assertTrue(any("配置" in row["title"] for row in rows))

    def test_duplicate_note_action_does_not_write_without_force(self):
        duplicate_content = "这是一段已经存在的足够长的笔记内容，用来验证重复检测是否生效。"
        existing = self.vault / "Notes" / "same.md"
        existing.parent.mkdir()
        existing.write_text(duplicate_content, encoding="utf-8")
        rows = main.query(QueryStub("note", duplicate_content), self.settings)
        note_row = next(row for row in rows if row.get("data", {}).get("kind") == "append-note")
        request = {"action": "save-note", "item": note_row}
        from contextlib import redirect_stdout
        import io
        output = io.StringIO()
        with redirect_stdout(output):
            main.action_result(request, self.settings)
        result = json.loads(output.getvalue())
        replacement = next(effect for effect in result["effects"] if effect["type"] == "replace")
        self.assertTrue(any(row["id"].startswith("force-save-") for row in replacement["items"]))
        self.assertFalse((self.vault / "Inbox" / "收集箱.md").exists())


    def test_template_without_frontmatter_gets_metadata(self):
        stamp = datetime(2026, 11, 10, 21, 30, 0, tzinfo=timezone.utc)
        result = main.ensure_frontmatter("# 简单模板\n\n正文", stamp, "项目记录")
        self.assertTrue(result.startswith("---\n"))
        self.assertIn('title: "项目记录"', result)
        self.assertIn('source: "Win顺"', result)
        self.assertIn('date: "2026-11-10"', result)

    def test_subprocess_query_protocol_json_and_no_side_effect(self):
        plugin_dir = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env.update({
            "WS_COMMAND": "note",
            "WS_QUERY": "一条协议查询测试内容",
            "WS_TEXT": "note 一条协议查询测试内容",
            "WS_SETTINGS": json.dumps({"vault_1": str(self.vault), "default_vault": "1", "open_after_save": False}, ensure_ascii=False),
        })
        proc = subprocess.run([sys.executable, str(plugin_dir / "main.py")], cwd=plugin_dir,
                              env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertIn("items", payload)
        self.assertFalse((self.vault / "Inbox" / "收集箱.md").exists())

    def test_action_request_writes_only_after_enter_action(self):
        plugin_dir = Path(__file__).resolve().parents[1]
        query_env = os.environ.copy()
        query_env.update({
            "WS_COMMAND": "note",
            "WS_QUERY": "真正写入动作测试内容",
            "WS_TEXT": "note 真正写入动作测试内容",
            "WS_SETTINGS": json.dumps({"vault_1": str(self.vault), "default_vault": "1", "open_after_save": False}, ensure_ascii=False),
        })
        query_proc = subprocess.run([sys.executable, str(plugin_dir / "main.py")], cwd=plugin_dir,
                                    env=query_env, capture_output=True, text=True, timeout=10)
        row = json.loads(query_proc.stdout)["items"][0]
        action_env = query_env.copy()
        action_env.update({"WS_ACTION": "save-note", "WS_ITEM": json.dumps(row, ensure_ascii=False)})
        action_proc = subprocess.run([sys.executable, str(plugin_dir / "main.py")], cwd=plugin_dir,
                                     env=action_env, capture_output=True, text=True, timeout=10)
        self.assertEqual(action_proc.returncode, 0, action_proc.stderr)
        effect_payload = json.loads(action_proc.stdout)
        self.assertIn("effects", effect_payload)
        target = self.vault / "Inbox" / "收集箱.md"
        self.assertTrue(target.exists())
        self.assertIn("真正写入动作测试内容", target.read_text(encoding="utf-8"))


    def test_dispatch_reports_error_instead_of_crashing(self):
        bad_settings = main.merged_settings({
            "vault_1": str(self.vault),
            "default_vault": "1",
            "daily_folder": str(self.vault / "Daily"),  # 绝对路径，safe_relative_path 会拒绝
            "open_after_save": False,
        })
        output = io.StringIO()
        errors = io.StringIO()
        with mock.patch.object(main.winshun, "settings", return_value=bad_settings), \
                mock.patch.object(main.winshun, "is_action", return_value=False), \
                mock.patch.object(main.winshun, "query", return_value=QueryStub("daily")), \
                redirect_stdout(output), redirect_stderr(errors):
            main.dispatch()

        payload = json.loads(output.getvalue())
        self.assertFalse(payload["items"][0]["valid"])
        self.assertIn("操作失败", payload["items"][0]["title"])
        self.assertIn("PluginError", errors.getvalue())

    def test_official_action_request_object_saves_note(self):
        rows = main.query(QueryStub("note", "经官方 SDK 对象保存的记录"), self.settings)
        row = next(row for row in rows if row.get("data", {}).get("kind") == "append-note")
        request = OfficialActionRequest(
            action="save-note", item=row, command="note", text="note 经官方 SDK 对象保存的记录"
        )
        self.assertFalse(hasattr(request, "get"))

        output = io.StringIO()
        with mock.patch.object(main.winshun, "settings", return_value=self.settings), \
                mock.patch.object(main.winshun, "is_action", return_value=True), \
                mock.patch.object(main.winshun, "action_request", return_value=request), \
                redirect_stdout(output):
            main.dispatch()

        payload = json.loads(output.getvalue())
        self.assertIn("effects", payload)
        target = self.vault / "Inbox" / "收集箱.md"
        self.assertTrue(target.exists())
        self.assertIn("经官方 SDK 对象保存的记录", target.read_text(encoding="utf-8"))


class ManifestTests(unittest.TestCase):
    def test_identity(self):
        plugin_dir = Path(__file__).resolve().parents[1]
        manifest = json.loads((plugin_dir / "plugin.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["id"], "888bik.obsidian-quicknote")
        self.assertEqual(manifest["id"], plugin_dir.name)
        self.assertEqual(manifest["version"], "1.0.2")


if __name__ == "__main__":
    unittest.main()
