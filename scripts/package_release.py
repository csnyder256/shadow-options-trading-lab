"""Create a deployment bundle from tracked tooling and explicitly built assets.

Private settings, dependencies, logs and local data cannot enter via a recursive
checkout copy. Run after the build, from a Git checkout, using Python 3.11+.
"""
import hashlib, json, shutil, subprocess, tarfile, tempfile, zipfile
from pathlib import Path
root = Path(__file__).resolve().parents[1]
config = json.loads((root / "release.json").read_text())
version = (root / "VERSION").read_text().strip()
name = config["name"] + "-v" + version + "-" + config.get("bundle", "deploy")
output = root / "dist-release"
output.mkdir(exist_ok=True)
tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
def safe(path):
    p = Path(path)
    return (not p.is_absolute() and ".." not in p.parts and
            not any(x in {".git", "node_modules", "__pycache__", "state", "secrets"} for x in p.parts) and
            (not p.name.startswith(".env") or p.name.endswith(".example")) and
            p.suffix not in {".db", ".sqlite", ".sqlite3", ".log", ".gba", ".gbc", ".gb"})
files = {p for p in tracked if p and safe(p) and not p.startswith((".github/", "tests/"))}
if config.get("include"):
    files = {p for p in files if any(p == x or p.startswith(x + "/") for x in config["include"])}
for folder in config.get("built", []):
    path = root / folder
    assert path.exists(), "Build output missing: " + folder
    files.update(str(p.relative_to(root)) for p in path.rglob("*") if p.is_file() and safe(str(p.relative_to(root))))
with tempfile.TemporaryDirectory() as temporary:
    stage = Path(temporary) / name
    stage.mkdir()
    for rel in sorted(files):
        src = root / rel
        assert src.is_file() and not src.is_symlink(), "Unexpected bundle member: " + rel
        dst = stage / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        dst.chmod(src.stat().st_mode & 0o777)
    manifest = {"project": config["name"], "version": version,
                "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root).decode().strip(),
                "files": {p: hashlib.sha256((stage / p).read_bytes()).hexdigest() for p in sorted(files)}}
    (stage / "release-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with tarfile.open(output / (name + ".tar.gz"), "w:gz") as tar:
        tar.add(stage, arcname=name)
    with zipfile.ZipFile(output / (name + ".zip"), "w", zipfile.ZIP_DEFLATED) as archive:
        for p in sorted(stage.rglob("*")):
            if p.is_file(): archive.write(p, str(Path(name) / p.relative_to(stage)))
for rel in config.get("extra_assets", []):
    assert safe(rel), "Unsafe extra asset"
    shutil.copyfile(root / rel, output / Path(rel).name)
assets = sorted(p for p in output.iterdir() if p.is_file() and p.name != "checksums.txt")
(output / "checksums.txt").write_text("".join(hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name + "\n" for p in assets))
print("Packaged", name, "with", len(files), "files")
