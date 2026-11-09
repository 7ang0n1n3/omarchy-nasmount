# Migration validation

Validated on 2026-11-09 against installed Omarchy shell sources. `/usr/share/omarchy/version` reports `4.0.0.alpha`; QtTest reports Qt 6.12.0 and platform product `omarchy 4.5.0`. The installed shell has no readable Git HEAD, so these identifiers are recorded separately rather than treating them as a single release identity.

## Observed

- `python3 -B -m unittest discover -s tests -v`: 19 tests passed. Temporary stores only; mount operations mocked. Includes stdin/legacy-payload rejection, credential retention and permissions, rename/delete, offline/partial reconciliation, locking, timeout/output limits, and staged idempotent installation/upgrade/removal.
- `QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software /usr/lib/qt6/bin/qmltestrunner -input tests/qml -import tests/qml/imports -o -,txt`: 17 QtTest passes, including init/cleanup. Uses narrow Quickshell process stubs. Covers status transitions, malformed/stale data, disabled/duplicate completion, request overlap, bounded stdin/output, retained action errors and markup-safe tooltips.
- `omarchy plugin validate .`: exit 0.
- Skill portable manifest/path checker: valid, no warnings or errors. Advisory security scan: no findings; expected manual-review capabilities for subprocesses, explicit installer and sudoers handling. This is not a security certification.
- `bash -n machine/omarchy-nasctl machine/90-omarchy-nas`: exit 0.
- `qmllint` using a temporary `qs` import alias to `/usr/share/omarchy/shell`: exit 0. Dynamic loader/host property and inherited unqualified-access warnings remain. `Service.qml` also passes standalone lint. This does not establish runtime popup geometry.

## Remaining deployment checks

No live machine installation, sudoers replacement, mount/unmount, real credential use, plugin enablement, desktop restart, or network transition was performed. These were outside the agreed source implementation scope.

After explicitly deploying the machine layer and plugin, check: discovery and own-service injection; one poller on multiple monitors; horizontal/vertical/tray anchoring; keyboard dismissal and popout switching; small-display scrolling; language/RTL behavior; hot reload, disable/remove, and shell restart; missing/old/unauthorized helper; actual SMB/NFS mount and network changes; no credential payloads in the complete process tree's argv or diagnostics. A replacement bar may not expose service lookup; the widget must show service unavailable there.

Existing mount paths outside `/mnt/nas` or unsupported custom options require administrator migration before using the new helper. Existing unmanaged sudoers grants require review. In-flight privileged operations have a helper deadline and may finish independently after the visual shell plugin closes.

`SOURCE-SHA256.txt` identifies the production snapshot reviewed during migration, before Git initialization. Subsequent changes are identified through Git history.
