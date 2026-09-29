"""Verify both published bundle formats and every file in their manifests."""
import hashlib, json, tarfile, zipfile
from pathlib import Path
root = Path(__file__).resolve().parents[1]
out = root / "dist-release"
for line in (out / "checksums.txt").read_text().splitlines():
    expected, name = line.split("  ", 1)
    assert Path(name).name == name
    assert hashlib.sha256((out / name).read_bytes()).hexdigest() == expected, name
for archive in out.glob("*.zip"):
    with zipfile.ZipFile(archive) as z:
        members = z.namelist()
        assert all(not Path(n).is_absolute() and ".." not in Path(n).parts for n in members)
        manifest_name = next(n for n in members if n.endswith("/release-manifest.json"))
        prefix = manifest_name.rsplit("/", 1)[0] + "/"
        manifest = json.loads(z.read(manifest_name))
        assert manifest["version"] == (root / "VERSION").read_text().strip()
        assert "DEPLOYMENT.md" in manifest["files"]
        for rel, expected in manifest["files"].items():
            assert hashlib.sha256(z.read(prefix + rel)).hexdigest() == expected, rel
            assert "node_modules" not in Path(rel).parts and "secrets" not in Path(rel).parts
            assert not Path(rel).name.startswith(".env") or rel.endswith(".example")
    with tarfile.open(archive.with_suffix(".tar.gz")) as t:
        for rel, expected in manifest["files"].items():
            assert hashlib.sha256(t.extractfile(prefix + rel).read()).hexdigest() == expected, rel
print("Archive manifests and SHA-256 checksums verified")
