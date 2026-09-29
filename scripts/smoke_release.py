"""Offline startup proof against the built image, with isolated disposable data."""
import argparse, json, subprocess, time, uuid
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument("image")
a = p.parse_args()
project = json.loads((Path(__file__).resolve().parents[1] / "release.json").read_text())["name"]
name = "release-smoke-" + uuid.uuid4().hex[:12]
def run(args, check=True):
    return subprocess.run(args, text=True, capture_output=True, check=check)
if project == "shadow-options-trading-lab":
    result = run(["docker", "run", "--rm", "--network", "none", a.image])
    assert "--once" in result.stdout
    print("Offline research CLI starts successfully")
    raise SystemExit(0)
port, route = {"openrouter-model-picker": (8080,"/"), "grain-bids-to-excel": (8383,"/"), "option-contract-grader": (8000,"/health")}[project]
volumes = {"grain-bids-to-excel": ["/opt/bidboard/app/data", "/opt/bidboard/Spreadsheets"], "option-contract-grader": ["/opt/option/data"]}.get(project, [])
args = ["docker", "run", "-d", "--name", name, "--network", "none", "--shm-size", "1g"]
for folder in volumes: args += ["--mount", "type=volume,dst=" + folder]
try:
    run(args + [a.image])
    assert run(["docker", "exec", name, "id", "-u"]).stdout.strip() != "0"
    if project == "openrouter-model-picker":
        probe = ["wget", "-qO-", "http://127.0.0.1:8080/"]
    else:
        probe = ["python", "-c", f"import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:{port}{route}', timeout=3).status == 200"]
    for attempt in range(40):
        result = run(["docker", "exec", name] + probe, check=False)
        if result.returncode == 0: break
        time.sleep(1)
    else:
        raise RuntimeError("Container did not serve its startup route")
    if project == "grain-bids-to-excel":
        run(["docker", "exec", name, "python", "-c", "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True, args=['--no-sandbox']); page=b.new_page(); page.set_content('<title>offline browser</title>'); assert page.title()=='offline browser'; b.close(); p.stop()"])
    if project == "openrouter-model-picker":
        run(["docker", "exec", name, "wget", "-qO-", "http://127.0.0.1:8080/lib/catalog.js"], check=True)
    print("Non-root offline startup and runtime dependencies verified")
finally:
    run(["docker", "rm", "-fv", name], check=False)
