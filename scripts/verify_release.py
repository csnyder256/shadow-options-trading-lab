"""Check release metadata without importing optional application dependencies."""
import json, os, re
from pathlib import Path
root = Path(__file__).resolve().parents[1]
version = (root / "VERSION").read_text().strip()
assert re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version), "Invalid release version"
ref = os.environ.get("GITHUB_REF", "")
if ref.startswith("refs/tags/"):
    assert ref == "refs/tags/v" + version, "Tag and VERSION disagree"
config = json.loads((root / "release.json").read_text())
for filename in config.get("package_json", []):
    assert json.loads((root / filename).read_text())["version"] == version, filename
for filename, pattern in config.get("version_patterns", {}).items():
    match = re.search(pattern, (root / filename).read_text())
    assert match and match.group(1) == version, filename
assert (root / "docs/releases" / ("v" + version + ".md")).is_file(), "Release notes missing"
notes = root / "docs/releases" / ("v" + version + ".md")
deployment_link = "https://github.com/csnyder256/" + config["name"] + "/blob/v" + version + "/DEPLOYMENT.md"
assert "(" + deployment_link + ")" in notes.read_text(), "Release notes need a version-specific deployment link"
print("Release metadata agrees on", version)
