"""Launch menu actions against the running desktop, including after a Nix rebuild."""
import json
import os
from pathlib import Path
import subprocess
import sys


def session_tree(instances):
    trees = {
        Path(instance["config_path"]).parent.parent
        for instance in instances
        if Path(instance["config_path"]).name == "shell.qml"
        and (Path(instance["config_path"]).parent / "plugins/menu/Menu.qml").is_file()
    }
    if len(trees) != 1:
        raise RuntimeError("Expected one running Omarchy shell on this display")
    return str(trees.pop())


def main():
    try:
        if sys.argv[1:] not in ([], ["keys"], ["toggle"]):
            raise ValueError("Usage: menu.py [keys|toggle]")
        instances = json.loads(subprocess.check_output(
            ["quickshell", "list", "--all", "--json"], text=True, timeout=5))
        os.environ["OMARCHY_PATH"] = session_tree(instances)
        command = (["bash", str(Path(__file__).with_name("keybindings.sh"))]
                   if sys.argv[1:] == ["keys"] else
                   ["omarchy-shell", "shell", "toggle" if sys.argv[1:] == ["toggle"] else "summon", "olafkfreund.github-actions", "{}"])
        os.execvp(command[0], command)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"GitHub Actions: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
