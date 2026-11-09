# NAS Auto Mount for Omarchy

NAS Auto Mount is an Omarchy Quattro plugin for connecting your Linux desktop to shared folders on a NAS (network-attached storage). It supports **SMB/CIFS and NFS**, shows mount status in the bar, and provides a popup for adding shares and mounting or unmounting them.

Associate a share with a NetworkManager connection, such as your home Wi-Fi or VPN, and the machine integration attempts to mount it when that connection becomes active. You can also choose to unmount it automatically when you leave that network.

For example, a share named `media` on `nas.example` can appear at `/mnt/nas/media` while you are connected to your home network. Once mounted, its files are accessible through your file manager and other applications.


## Features

- Add, edit, and remove SMB/CIFS or NFS shares from the bar popup.
- Configure the NAS server, remote share/export, local mount point, local Linux owner, and network association.
- Enter SMB credentials or retain previously saved credentials when editing.
- Mount or unmount individual shares, or all configured shares.
- See the active network, mounted shares, missing credentials, and backend errors.
- Automatically reconcile mounts after NetworkManager connection changes and successful saves.
- Share one status service across monitors, with a configurable refresh interval of 2–60 seconds (5 seconds by default).

This plugin connects to existing NAS shares. It does not create shares on the NAS, configure the NAS server, synchronize files, or provide backups.

## How it works

The project has two separately installed parts:

| Part | Responsibility |
| --- | --- |
| Quattro plugin | Bar button, configuration popup, shared status polling, and requests for mount operations. |
| Machine integration | Privileged mount/unmount commands, saved configuration and credentials, and automatic mounting through a NetworkManager dispatcher hook. |

The plugin runs inside the existing Omarchy shell. The machine integration uses `omarchy-nasctl` and a root-owned Python helper; it does not add a background daemon or systemd service.

Automatic mounting belongs to the machine integration, so it continues to respond to network changes even when the shell plugin is disabled or removed. Status polling only observes mounts; it is not a continuous automatic-mount retry loop.

## Requirements

- Omarchy with the Quattro plugin host and Quickshell.
- NetworkManager managing the connections associated with your shares.
- Python 3.10 or newer, sudo (including `visudo`), util-linux, cifs-utils, and nfs-utils.
- An existing, reachable SMB/CIFS share or NFS export with suitable server-side permissions.

The current plugin version is **0.3.0** and requires **machine protocol 1**. Installing the shell plugin alone does not install the privileged helper or its dependencies.

## Setup

Run these commands in a terminal on your Omarchy desktop.

### 1. Install dependencies and the machine integration

Install the required packages, then clone the repository:

```sh
sudo pacman -S --needed git python sudo networkmanager util-linux cifs-utils nfs-utils
git clone https://github.com/7ang0n1n3/omarchy-nasmount.git
cd omarchy-nasmount
```

If you already have a checkout, enter that directory instead of cloning it again.

Review the files in `machine/`, then install the helper for your current Linux user:

```sh
sudo python3 machine/setup.py install --user "$USER"
```

Run this from your normal user session so `$USER` identifies the account that uses the desktop. Setup installs the CLI, root helper, NetworkManager dispatcher, and a passwordless sudo rule limited to the NAS helper. The selected user can administer all shares in this machine's NAS configuration.

Setup preserves existing configuration and credentials. If it reports an unmanaged `/etc/sudoers.d/omarchy-nas` rule, stop and review the existing rule before continuing; setup will not overwrite it.

### 2. Install and enable the shell plugin

```sh
omarchy plugin add https://github.com/7ang0n1n3/omarchy-nasmount.git --enable
```

Its plugin ID is `io.github.tangonine.omarchy-nas`, and its default bar section is the right side. The NAS icon should appear after the plugin is enabled.

If the plugin is already installed, including a manually copied local version, enable it instead of adding it again:

```sh
omarchy plugin enable io.github.tangonine.omarchy-nas --section right
```

Enabling an existing installation does not update its files or convert a manually copied installation into a Git-based one.

`omarchy plugin add` handles plugin files and enablement; it does not run `machine/setup.py`, install packages, or configure privileged access. Both steps above are required for a new installation.

### 3. Add a share

1. Left-click the NAS bar icon and select **Add NAS**.
2. Choose **SMB/CIFS** or **NFS**.
3. Enter a name, server address, and SMB share name or NFS export path.
4. Set a local mount point, such as `/mnt/nas/media`, and your Linux username.
5. Select the network association by entering the NetworkManager connection name or using **Use current network**.
6. For SMB, enter the username, password, and optional domain.
7. Choose whether to automatically unmount when leaving that network, then save.

Saving attempts to bring the mounts into line with the currently active connections. Manual **Mount**, **Unmount**, **Mount all**, and **Unmount all** controls are also available. **Refresh** and middle-clicking the bar icon update status.

## Configuration and credentials

| Location | Contents |
| --- | --- |
| `/etc/omarchy-nas/config.json` | Share definitions and network associations. |
| `/etc/omarchy-nas/credentials/` | SMB credential files owned by the machine integration. |
| Omarchy widget settings | Status refresh interval. |

Credentials are sent to the helper through standard input, not command-line arguments. Password fields are cleared after submission and when the popup closes. Stored credentials are root-protected files, not an encrypted keychain: directories use mode `0700` and credential files use `0600`.

When editing a share, leave its SMB username and password blank to keep saved credentials. Removing a share from the popup unmounts it and deletes its configuration and saved credential file; it does not delete files on the NAS.

## Mount restrictions and upgrades

- Local mount points must be below `/mnt/nas`, without symlinks or user-writable ancestor directories.
- Mount options are allowlisted, and `nosuid,nodev,noexec` are enforced.
- Unmount a share before changing its identity, protocol, remote location, local mount point, owner, or mount options.
- Upgrade the machine integration before upgrading the shell plugin. Legacy Base64 command-line credential saves are unsupported.
- Back up existing NAS configuration and credentials privately before upgrading. Older mount paths outside `/mnt/nas`, custom mount options, and existing sudoers grants may require administrator review.

Operations have time and output limits. If a request times out, refresh status before retrying because part of the operation may already have completed.

## Removal

Remove only the shell plugin with:

```sh
omarchy plugin remove io.github.tangonine.omarchy-nas
```

This leaves the machine integration, current mounts, configuration, and credentials in place.

To also remove the machine integration, unmount any shares you want disconnected first, then run:

```sh
sudo python3 machine/setup.py remove
```

Machine removal deletes the dispatcher, managed sudoers rule, and installed executables. It retains existing mounts, configuration, credentials, and mount directories, and does not uninstall packages.

## Development and validation

See [CHANGELOG.md](CHANGELOG.md) for version history and notable changes.

Run the available checks with one command:

```sh
python3 -B scripts/check.py --require-qml
```

Python tests use temporary stores and mocked mount operations. QML tests use process stubs, so they do not invoke the installed NAS helper. Omarchy host validation runs when its CLI is installed. See [CONTRIBUTING.md](CONTRIBUTING.md) for dependencies and options, and [VALIDATION.md](VALIDATION.md) for recorded results and remaining live checks.

## License

[MIT](LICENSE), as declared in the plugin manifest.
