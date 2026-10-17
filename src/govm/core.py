"""Core logic: download, extract, switch, list Go toolchains."""

from __future__ import annotations

import json
import os
import platform
import shutil
import tarfile
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from tqdm import tqdm

GOVM_ROOT = Path(os.environ.get("GOVM_ROOT", Path.home() / ".govm"))
VERSIONS_DIR = GOVM_ROOT / "versions"
BIN_DIR = GOVM_ROOT / "bin"
CURRENT_LINK = GOVM_ROOT / "current"

DOWNLOAD_BASE = "https://go.dev/dl"
RELEASES_URL = f"{DOWNLOAD_BASE}/?mode=json&include=all"

# Binaries exposed as shims in BIN_DIR.
SHIMS = ("go", "gofmt")

# Markers so we can find/refresh our own block in a shell rc file.
RC_BEGIN = "# >>> govm initialize >>>"
RC_END = "# <<< govm initialize <<<"


class GovmError(Exception):
    """User-facing failure."""


@dataclass(frozen=True)
class Release:
    version: str  # "go1.22.0"
    stable: bool
    files: list[dict]

    @property
    def short(self) -> str:
        return self.version.removeprefix("go")


def detect_platform() -> tuple[str, str]:
    """Return (os, arch) in Go's naming scheme."""
    os_map = {"linux": "linux", "darwin": "darwin", "windows": "windows"}
    arch_map = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}

    sysname = platform.system().lower()
    machine = platform.machine().lower()

    goos = os_map.get(sysname)
    goarch = arch_map.get(machine)
    if not goos or not goarch:
        raise GovmError(f"Unsupported platform: {sysname}/{machine}")
    return goos, goarch


def _fetch_json(url: str) -> list[dict]:
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.load(resp)
    except OSError as exc:
        raise GovmError(f"Failed to fetch release list: {exc}") from exc


def list_releases() -> list[Release]:
    return [
        Release(version=item["version"], stable=item.get("stable", False), files=item.get("files", []))
        for item in _fetch_json(RELEASES_URL)
    ]


def normalize(version: str) -> str:
    """'1.22.0' or 'go1.22.0' -> 'go1.22.0'."""
    version = version.strip()
    return version if version.startswith("go") else f"go{version}"


def installed_versions() -> list[str]:
    if not VERSIONS_DIR.is_dir():
        return []
    return sorted(
        (p.name for p in VERSIONS_DIR.iterdir() if p.is_dir()),
        key=_version_key,
    )


def _version_key(version: str) -> tuple:
    parts = version.removeprefix("go").split(".")
    key: list = []
    for part in parts:
        head = part.split("rc")[0].split("beta")[0]
        key.append(int(head) if head.isdigit() else 0)
        # rc/beta sort before the final release of the same number.
        key.append(0 if "rc" in part or "beta" in part else 1)
    return tuple(key)


def current_version() -> str | None:
    if CURRENT_LINK.is_symlink():
        return os.readlink(CURRENT_LINK).rstrip("/").split("/")[-1]
    if CURRENT_LINK.is_dir():
        return CURRENT_LINK.name
    return None


def _find_file(release: Release, goos: str, goarch: str) -> dict:
    for f in release.files:
        if f.get("os") == goos and f.get("arch") == goarch and f.get("kind") == "archive":
            return f
    raise GovmError(
        f"No build of {release.version} for {goos}/{goarch}. "
        "Run `govm remote --all` for the full list."
    )


def _download(url: str, dest: Path) -> None:
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            with (
                tqdm(
                    total=total or None,
                    desc=f"Downloading {dest.name}",
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                    disable=None,
                ) as bar,
                open(dest, "wb") as out,
            ):
                while chunk := resp.read(256 * 1024):
                    out.write(chunk)
                    bar.update(len(chunk))
    except OSError as exc:
        raise GovmError(f"Download failed: {exc}") from exc


def _extract(archive: Path, dest: Path) -> None:
    """Extract an archive into dest, showing per-file progress."""
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            members = zf.infolist()
            for info in tqdm(members, desc="Extracting", unit="file", disable=None):
                zf.extract(info, dest)
    else:
        with tarfile.open(archive, "r:gz") as tf:
            members = tf.getmembers()
            for member in tqdm(members, desc="Extracting", unit="file", disable=None):
                # filter="data" blocks path traversal / unsafe links.
                tf.extract(member, dest, filter="data")


def _remove_tree(path: Path, desc: str = "Removing") -> None:
    """Delete a tree file by file so the progress bar can advance."""
    files = [p for p in path.rglob("*") if not p.is_dir()]
    with tqdm(total=len(files), desc=desc, unit="file", disable=None) as bar:
        for file in files:
            file.unlink(missing_ok=True)
            bar.update(1)
    shutil.rmtree(path, ignore_errors=True)


def install(version: str, force: bool = False) -> Path:
    """Download + extract a Go release into VERSIONS_DIR. Returns its path."""
    version = normalize(version)
    target = VERSIONS_DIR / version

    if target.is_dir() and not force:
        raise GovmError(f"{version} is already installed. Use --force to reinstall.")
    if target.exists():
        _remove_tree(target)

    goos, goarch = detect_platform()
    releases = {r.version: r for r in list_releases()}
    release = releases.get(version)
    if release is None:
        raise GovmError(f"Version '{version}' not found. See `govm remote`.")

    file = _find_file(release, goos, goarch)
    url = f"{DOWNLOAD_BASE}/{file['filename']}"

    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=GOVM_ROOT) as tmp:
        tmp_path = Path(tmp)
        archive = tmp_path / file["filename"]
        _download(url, archive)
        _extract(archive, tmp_path)

        # Go archives contain a single top-level dir ("go" for tar.gz, version-named for zip).
        extracted = next(
            (tmp_path / name for name in (version, "go") if (tmp_path / name).is_dir()),
            None,
        )
        if extracted is None:
            raise GovmError(f"Unexpected archive layout: {version} not found after extract.")
        shutil.move(str(extracted), str(target))

    return target


def use(version: str, update_path: bool = True) -> Path:
    """Point CURRENT_LINK at an installed version and refresh shims."""
    version = normalize(version)
    target = VERSIONS_DIR / version
    if not target.is_dir():
        raise GovmError(f"{version} is not installed. Run `govm install {version}`.")

    if CURRENT_LINK.is_symlink() or CURRENT_LINK.is_file():
        CURRENT_LINK.unlink()
    elif CURRENT_LINK.is_dir():
        shutil.rmtree(CURRENT_LINK)
    CURRENT_LINK.symlink_to(target, target_is_directory=True)

    _refresh_shims(target)
    if update_path:
        ensure_path()
    return target


def _refresh_shims(target: Path) -> None:
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    for name in SHIMS:
        real = target / "bin" / name
        if not real.exists():
            continue
        link = BIN_DIR / name
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(real)


def _rc_candidates() -> list[Path]:
    """Shell rc files to try, most likely first, based on $SHELL."""
    home = Path.home()
    shell = Path(os.environ.get("SHELL", "")).name
    if shell == "fish":
        return [home / ".config" / "fish" / "config.fish"]
    if shell == "zsh":
        return [home / ".zshrc"]
    if shell == "bash":
        return [home / ".bashrc", home / ".bash_profile"]
    return [home / ".profile"]


def _path_line(rc: Path) -> str:
    if rc.name == "config.fish":
        return f"fish_add_path {BIN_DIR}"
    return f'export PATH="{BIN_DIR}:$PATH"'


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def path_configured() -> Path | None:
    """Return the rc file that already has our PATH block, if any."""
    for rc in _rc_candidates():
        if rc.is_file() and RC_BEGIN in _read(rc):
            return rc
    return None


def ensure_path() -> Path | None:
    """Add BIN_DIR to the user's PATH via their shell rc. Idempotent.

    Returns the rc file that was modified, or None if already configured.
    """
    existing = path_configured()
    if existing is not None:
        return None

    rc = _rc_candidates()[0]
    rc.parent.mkdir(parents=True, exist_ok=True)
    block = f"\n{RC_BEGIN}\n{_path_line(rc)}\n{RC_END}\n"
    try:
        with rc.open("a", encoding="utf-8") as f:
            f.write(block)
    except OSError as exc:
        raise GovmError(f"Could not update {rc}: {exc}") from exc
    return rc


def uninstall(version: str) -> None:
    version = normalize(version)
    target = VERSIONS_DIR / version
    if not target.is_dir():
        raise GovmError(f"{version} is not installed.")

    was_current = current_version() == version
    if was_current:
        CURRENT_LINK.unlink(missing_ok=True)
    _remove_tree(target, desc=f"Removing {version}")

    if was_current:
        remaining = installed_versions()
        if remaining:
            use(remaining[-1])
            print(f"Active version moved to {remaining[-1]}")
        else:
            for name in SHIMS:
                (BIN_DIR / name).unlink(missing_ok=True)


def env_report() -> str:
    goos, goarch = detect_platform()
    current = current_version()
    lines = [
        f"GOVM_ROOT   = {GOVM_ROOT}",
        f"platform    = {goos}/{goarch}",
        f"current     = {current or '(none)'}",
        f"PATH shim   = {BIN_DIR}",
    ]
    rc = path_configured()
    if rc is not None:
        lines.append(f"PATH setup  = configured in {rc}")
    else:
        lines += [
            "",
            "PATH is not set up yet. It is added automatically by `govm use`,",
            "or add it manually:",
            f'  export PATH="{BIN_DIR}:$PATH"',
        ]
    return "\n".join(lines)
