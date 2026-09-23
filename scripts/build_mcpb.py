"""Build dist/osint-toolbox-mcp-<version>.mcpb, the MCP bundle desktop clients install with one click."""

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from osint_toolbox_mcp import __version__  # noqa: E402


def main() -> None:
    bundle_path = ROOT / "dist" / f"osint-toolbox-mcp-{__version__}.mcpb"
    bundle_path.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name in ("manifest.json", "pyproject.toml", "icon.png"):
            bundle.write(ROOT / "mcpb" / name, name)
        bundle.write(ROOT / "mcpb" / "main.py", "src/main.py")
        for module in sorted((ROOT / "src" / "osint_toolbox_mcp").glob("*.py")):
            bundle.write(module, f"src/osint_toolbox_mcp/{module.name}")
        bundle.write(ROOT / "LICENSE", "LICENSE")
    print(bundle_path)


if __name__ == "__main__":
    main()
