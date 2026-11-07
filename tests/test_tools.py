import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kareem_ai.storage import Store, new_chat
from kareem_ai.tools import execute, prepare, proposals, run_python


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_preview_never_writes_and_execution_matches_preview(self):
        action = {"type": "write_file", "path": "test.txt", "content": "hello\n"}
        proposed = prepare(action, self.root)
        self.assertFalse((self.root / "test.txt").exists())
        self.assertIn("+hello", proposed.preview)
        action["content"] = "changed after preview"
        execute(proposed)
        self.assertEqual((self.root / "test.txt").read_text(), "hello\n")

    def test_modified_file_requires_new_approval(self):
        file = self.root / "a.txt"
        file.write_text("old")
        proposed = prepare({"type": "write_file", "path": "a.txt", "content": "new"}, self.root)
        file.write_text("human edit")
        with self.assertRaisesRegex(ValueError, "changed since preview"):
            execute(proposed)
        self.assertEqual(file.read_text(), "human edit")

    def test_path_escape_and_protected_folders(self):
        for path in ("../escape", "C:/Windows/file", "x:stream", "sources/test.txt", ".git/config", ".aws/key"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                prepare({"type": "write_file", "path": path, "content": "bad"}, self.root)

    def test_no_folder_no_file_access(self):
        with self.assertRaises(ValueError):
            prepare({"type": "read_file", "path": "test"})

    def test_read_and_list(self):
        (self.root / "a.txt").write_text("content")
        self.assertEqual(execute(prepare({"type": "read_file", "path": "a.txt"}, self.root)), "content")
        self.assertIn("a.txt", execute(prepare({"type": "list_files", "path": "."}, self.root)))

    def test_browser_needs_valid_url_and_executor(self):
        for url in ("file:///C:/secret", "javascript:alert(1)", "https://user:pass@example.com", "http://example.com"):
            with self.assertRaises(ValueError):
                prepare({"type": "open_url", "url": url})
        action = prepare({"type": "open_url", "url": "https://example.com"})
        with self.assertRaises(ValueError):
            execute(action)
        opened = []
        execute(action, lambda url: opened.append(url) or True)
        self.assertEqual(opened, ["https://example.com"])

    def test_no_host_code_fallback(self):
        with patch("shutil.which", return_value=None), patch("subprocess.Popen") as spawn:
            with self.assertRaisesRegex(ValueError, "Docker"):
                run_python("print('hello')")
            spawn.assert_not_called()

    def test_unsupported_action_and_bad_json(self):
        self.assertEqual(proposals('```action\n{"type":"shell","command":"bad"}\n```'), [])
        self.assertEqual(proposals('```action\nbad json\n```'), [])
        with self.assertRaises(ValueError):
            prepare({"type": "shell"})

    def test_link_escape(self):
        outside = self.root.parent / (self.root.name + "-outside")
        outside.mkdir(exist_ok=True)
        link = self.root / "link"
        try:
            try:
                link.symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("Windows symlink permission unavailable")
            with self.assertRaises(ValueError):
                prepare({"type": "write_file", "path": "link/no.txt", "content": "bad"}, self.root)
        finally:
            if link.is_symlink():
                link.unlink()
            outside.rmdir()

    def test_storage_roundtrip_and_no_keys_in_config(self):
        store = Store(self.root)
        chat = new_chat()
        chat["messages"].append({"role": "user", "content": "hello"})
        store.save_chat(chat)
        self.assertEqual(store.chats()[0]["messages"][0]["content"], "hello")
        store.save_config({"Gemini": "model", "secret": "should-not-save"})
        self.assertNotIn("should-not-save", (self.root / "settings.json").read_text())


if __name__ == "__main__":
    unittest.main()
