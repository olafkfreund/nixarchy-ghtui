import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("menu", Path(__file__).resolve().parents[1] / "menu.py")
menu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(menu)


class MenuTest(unittest.TestCase):
    def test_running_tree_and_ambiguous_instances(self):
        with tempfile.TemporaryDirectory() as directory:
            trees = [Path(directory) / name for name in ("running", "other")]
            for tree in trees:
                marker = tree / "shell/plugins/menu/Menu.qml"
                marker.parent.mkdir(parents=True)
                marker.touch()
            instances = [{"config_path": str(tree / "shell/shell.qml")} for tree in trees]
            self.assertEqual(menu.session_tree(instances[:1]), str(trees[0]))
            self.assertEqual(menu.session_tree(instances[:1] * 2), str(trees[0]))
            with self.assertRaises(RuntimeError):
                menu.session_tree(instances)
            with self.assertRaises(RuntimeError):
                menu.session_tree([])
            with self.assertRaises(RuntimeError):
                menu.session_tree([{"config_path": str(Path(directory) / "unrelated/shell.qml")}])
