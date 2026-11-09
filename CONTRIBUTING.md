# Contributing

## Project layout

- `manifest.json`, `BarWidget.qml`, `Panel.qml`, `Service.qml`, `UiText.js`: hosted Quattro plugin.
- `i18n/`: plugin translations.
- `machine/`: separately installed CLI, privileged helper, dispatcher and setup/removal tool.
- `tests/`: fictional fixtures and QML process stubs.
- `scripts/check.py`: repository validation entry point.

## Local checks

Use Linux with Python 3.10 or newer and Bash. Qt 6 Quick/QtTest and `qmltestrunner` enable the QML tests; an installed Omarchy host enables full host manifest validation.

```sh
python3 -B scripts/check.py
```

Use `--require-qml` to make missing Qt tests a failure. Set `QMLTESTRUNNER` to an absolute Qt 6 runner path when it is not discovered automatically. Skipped host checks are reported explicitly. The command never installs the plugin, invokes real mounts, or updates sudoers.

Keep machine fixtures in temporary directories and use fictional credentials. Do not commit `/etc/omarchy-nas` data, private backups, or real NAS credentials. Changes to the privileged helper need tests for the affected authorization, validation, storage, and failure paths.

## Compatibility

Keep the root manifest so Omarchy can install the repository directly. Keep machine setup explicit: plugin add/update/remove must not provision privileged files or delete NAS data. Update the machine protocol when changing the CLI contract and document upgrade order in the README.

`VALIDATION.md` records the migration's observed results and outstanding live checks. `SOURCE-SHA256.txt` identifies that historical production snapshot; it is not a checksum gate for future changes. Use Git commits to identify subsequent source versions.

Before release, run the tests and exercise the affected live shell and machine behavior. Report unrun checks rather than treating portable tests as proof of live integration.
