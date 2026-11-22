{
  description = "GitHub Actions panel for the Omarchy shell";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
      version = (builtins.fromJSON (builtins.readFile ./manifest.json)).version;
      runtimeFiles = [
        "LICENSE"
        "manifest.json"
        "ActionsPanel.qml"
        "ActionsModel.js"
        "Polling.js"
        "actions.py"
        "menu.py"
        "menu.example.json"
        "keybindings.sh"
      ];
    in
    {
      packages = forAllSystems (pkgs: {
        default =
          pkgs.runCommand "nixarchy-ghtui-${version}"
            {
              inherit version;
              # Found on PATH at run time, not substituted, so Git installs keep working (#32).
              passthru.runtimeDeps = [
                pkgs.gh
                pkgs.python3
                pkgs.xdg-utils
                pkgs.wl-clipboard
                pkgs.less
                pkgs.libnotify
              ];
            }
            ''
              mkdir -p "$out"
              ${nixpkgs.lib.concatMapStringsSep "\n" (file: ''
                cp ${./. + "/${file}"} "$out/${file}"
              '') runtimeFiles}
            '';
        bar =
          pkgs.runCommand "nixarchy-ghtui-bar-${version}"
            {
              inherit version;
            }
            ''
              mkdir -p "$out"
              cp ${./bar-widget}/* "$out/"
            '';
      });

      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = [
            pkgs.quickshell
            pkgs.sway
            pkgs.wtype
            pkgs.python3
          ];
        };
      });

      checks = forAllSystems (pkgs: {
        plugin =
          pkgs.runCommand "nixarchy-ghtui-checks-${version}"
            {
              nativeBuildInputs = [
                pkgs.python3
                pkgs.nodejs
              ];
            }
            ''
              plugin=${self.packages.${pkgs.stdenv.hostPlatform.system}.default}
              bar=${self.packages.${pkgs.stdenv.hostPlatform.system}.bar}
              python3 - "$plugin" "$bar" <<'PY'
              import json, sys
              from pathlib import Path
              root = Path(sys.argv[1])
              bar = Path(sys.argv[2])
              assert sorted(p.name for p in root.iterdir()) == sorted(${builtins.toJSON runtimeFiles})
              assert (root / 'LICENSE').is_file(), 'the package must ship its licence'
              assert not any(p.is_symlink() for p in root.rglob('*'))
              manifest = json.loads((root / 'manifest.json').read_text())
              assert manifest['version'] == '${version}'
              assert manifest['id'] == 'olafkfreund.github-actions'
              assert all((root / entry).is_file() for entry in manifest['entryPoints'].values())
              assert sorted(p.name for p in bar.iterdir()) == sorted(['manifest.json', 'BarWidget.qml', 'BarModel.js', 'LICENSE'])
              assert (bar / 'LICENSE').read_bytes() == (root / 'LICENSE').read_bytes()
              assert not any(p.is_symlink() for p in bar.rglob('*'))
              bar_manifest = json.loads((bar / 'manifest.json').read_text())
              assert bar_manifest['id'] == 'olafkfreund.github-actions-bar'
              assert bar_manifest['kinds'] == ['bar-widget']
              assert bar_manifest['entryPoints'] == {'barWidget': 'BarWidget.qml'}
              assert (bar / bar_manifest['entryPoints']['barWidget']).is_file()
              assert bar_manifest['version'] == manifest['version']
              PY
              cp "$plugin"/* .
              mkdir -p bar-widget
              cp "$bar/BarModel.js" bar-widget/
              cp -R ${./tests} tests
              export HOME="$TMPDIR/home"
              mkdir -p "$HOME"
              python3 -m unittest discover -s tests -v
              node tests/model.cjs
              node tests/polling.cjs
              node tests/bar.cjs
              python3 menu.py register
              bash keybindings.sh --print > /dev/null
              touch "$out"
            '';
      });
    };
}
