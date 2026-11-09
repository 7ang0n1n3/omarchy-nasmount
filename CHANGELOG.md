# Changelog

Notable changes to NAS Auto Mount for Omarchy are recorded here, newest first.

## Unreleased

### Added

- This changelog, with the initial repository version documented below.

### Changed

- Clarified installation from the GitHub repository, including dependency installation, machine setup, and enabling an existing plugin installation.

## 0.3.0 — Initial repository version (2026-11-09)

This version was imported in the initial Git commit. The date records that import; no release tag exists in the repository.

### Added

- Omarchy Quattro bar widget and popup for adding, editing, and removing SMB/CIFS and NFS shares.
- Individual and bulk mount/unmount controls, network status, and mount error reporting.
- Shared status polling across monitors with a configurable refresh interval of 2–60 seconds.
- Separate machine integration with a CLI, privileged Python helper, setup/removal tool, and NetworkManager dispatcher for automatic mounting and optional unmounting on network changes.
- Root-protected SMB credential storage with credentials submitted through standard input.
- Mount path restrictions under `/mnt/nas`, allowlisted options, and enforced `nosuid,nodev,noexec` flags.
- Python tests, QML service tests with process stubs, and a repository validation command.
- Installation, configuration, upgrade, removal, contribution, and validation documentation.

### Compatibility

- Requires machine protocol 1 and a separately installed machine integration.
- Upgrade the machine integration before the shell plugin. Legacy Base64 command-line credential saves are unsupported.
