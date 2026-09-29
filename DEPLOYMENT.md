# Install and update ATLAS

## Linux or Docker Desktop research environment

Extract the `v0.1.1` deployment ZIP or tarball from [Releases](https://github.com/csnyder256/shadow-options-trading-lab/releases). Check SHA-256 against `checksums.txt`. Build and inspect the CLI:

```sh
docker compose -p atlas build
docker compose -p atlas run --rm atlas
```

The default prints help and exits. The image includes Python 3.14 and the research dependencies. Configuration is mounted at runtime, read-only; no credentials or private configuration are built into the image. Review the supplied `config` examples and configure your own data feeds following README before running a research tick:

```sh
docker compose -p atlas run --rm atlas scripts/run_strategy_lab.py --once --no-hub
```

This command writes research state to the persistent `atlas-runtime` volume and may access configured market data. It is a shadow ledger runner with no order-placement path. It does not install Windows UI automation, Scout models, or broker desktop software. Those optional paths retain their own setup instructions.

For Playwright screenshots, build the optional image target:

```sh
docker build --target vision -t atlas-vision .
docker run --rm atlas-vision -m playwright --help
```

Chromium and OS libraries are included in that target. Core builds avoid the browser download. Mount only the configuration and runtime directories needed by the script you run; optional collectors may require additional data mounts.

## Python install

The same bundle supports the existing Python 3.14 virtual environment workflow in README, on Windows or Linux. Install `requirements.txt` in a fresh environment, then invoke scripts from the project root with `PYTHONPATH=.`.

## Upgrade and backup

Stop research processes before exporting the named runtime volume (Docker Desktop or a temporary archive container). Keep a separate copy of private `config`, credentials, data and ledgers. Extract the new release to a separate directory and use the same Compose project name to reuse the volume. Restore your reviewed configuration there before running. Retain the previous release and its matching ledger backup for rollback. Never replace a live ledger with the release's examples.
