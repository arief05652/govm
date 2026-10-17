# govm

A small Go version manager written in Python.

`govm` lets you install several Go toolchains side by side, switch between
them at any time, and keep your system Go installation untouched. Each version
lives in its own directory, and a single `govm use` command decides which one
`go` resolves to.

## Features

- Install any released Go version into an isolated directory.
- Switch the active version instantly, without re-downloading.
- List installed versions and the one currently active.
- Browse available versions straight from the official `go.dev` release feed.
- Uninstall versions you no longer need.
- Progress bars for download, extraction and removal.
- Adds itself to your `PATH` automatically on first use.
- Never modifies a system-wide Go install.

## Requirements

- Python 3.12 or newer.
- Linux or macOS on `amd64` or `arm64`. Windows is untested for now.
- A network connection for installing and listing versions.

## Installation

Install as a standalone tool with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install .
```

Or from a Git repository:

```bash
uv tool install git+https://github.com/arief05652/govm
```

With [pipx](https://pipx.pypa.io/):

```bash
pipx install .
```

For local development:

```bash
uv sync
uv run govm --help
```

## Quick start

```bash
govm remote           # see what is available
govm install 1.22.0   # download and extract it
govm use 1.22.0       # make it the active version
go version            # -> go version go1.22.0 ...
```

## Commands

| Command | Description |
| --- | --- |
| `govm install VERSION` | Download and install a Go version. `VERSION` may be `1.22.0` or `go1.22.0`. Use `--force` to reinstall an existing one. |
| `govm use VERSION` | Switch the active version and refresh the shims. Use `--no-path` to skip editing your shell rc. |
| `govm list` | Show installed versions. `*` marks the active one. |
| `govm current` | Print the active version. |
| `govm uninstall VERSION` | Remove an installed version. If it was active, the newest remaining version takes over. |
| `govm remote` | List versions available for download. `--all` includes rc/beta; `--limit N` controls how many rows are shown (default 15). |
| `govm env` | Show paths, detected platform, the active version, and whether `PATH` is configured. |
| `govm --version` | Print the govm version. |

Run `govm <command> --help` for details on any command.

## How it works

Everything is stored under `~/.govm`:

```
~/.govm/
├── versions/
│   ├── go1.21.0/        # a complete Go toolchain
│   └── go1.22.0/
├── current -> versions/go1.22.0
└── bin/
    ├── go               # shim pointing at the active version
    └── gofmt
```

`govm use` repoints `current` and the `bin/` shims at the chosen version.
Because `bin/` is on your `PATH`, the `go` command follows whatever version
is active. Your distro or system Go installation is never touched.

## PATH setup

You do not need to configure anything by hand. The first time you run
`govm use`, it appends a small marked block to your shell startup file:

| Shell | File |
| --- | --- |
| bash | `~/.bashrc` |
| zsh | `~/.zshrc` |
| fish | `~/.config/fish/config.fish` |
| other | `~/.profile` |

Open a new terminal (or re-source the file) for it to take effect. The block
is only added once, and `govm use --no-path` skips it entirely.

To do it manually:

```bash
# bash / zsh
export PATH="$HOME/.govm/bin:$PATH"

# fish
fish_add_path $HOME/.govm/bin
```

Run `govm env` to confirm that `PATH` is set up.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `GOVM_ROOT` | `~/.govm` | Where versions, shims and the active pointer are stored. |

Set it before running `govm` to relocate everything:

```bash
export GOVM_ROOT=/opt/govm
```

## Uninstalling govm

Remove the marked block that `govm use` added to your shell rc, then delete
`~/.govm`. If you installed the tool itself with uv or pipx, remove it the same
way:

```bash
uv tool uninstall govm
# or
pipx uninstall govm
```

## Platform support

| OS | Architecture | Status |
| --- | --- | --- |
| Linux | amd64, arm64 | Supported |
| macOS | amd64, arm64 | Supported |
| Windows | amd64, arm64 | Untested |

On Windows the current implementation relies on symlinks for the active version
and shims, which need Administrator rights or Developer Mode, and the automatic
`PATH` setup targets POSIX shells. Treat Windows as unverified for now.

## Limitations

- `remote` and `install` depend on the official `go.dev` JSON API.
- Downloads are not checksum-verified yet, although the API provides SHA256.
- Only `go` and `gofmt` are exposed as shims.
- Downloads are not resumed; an interrupted install starts over.
- Windows support is untested (see Platform support).

## License

Licensed under the GNU General Public License v3.0 or later
([GPL-3.0-or-later](https://www.gnu.org/licenses/gpl-3.0.html)).

You are free to use, study, share and modify this project. Any distributed
version or derivative work must also be released under the GPL and must make
its source code available.

See the `LICENSE` file for the full text.
