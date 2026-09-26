#!/usr/bin/env python3
"""Build the Cynqra desktop app for one platform: a Windows installer, a macOS disk image or a
Linux archive. Runs on the matching GitHub runner (.github/workflows/cynqra-desktop.yml).

    python desktop/build.py --target windows-x64
    python desktop/build.py --target macos-arm64
    python desktop/build.py --target linux-x64

What goes in, each pinned and checked against a SHA-256:
  * CPython from python-build-standalone: a relocatable interpreter, nothing to install
  * llama.cpp's llama-server release build: the CPU build, plus Vulkan (Windows, Linux) or
    Metal (macOS) for the GPU
  * the app itself, poc/ without tests and research, precompiled
Output goes to dist/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import shutil
import struct
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESKTOP = ROOT / "desktop"
VERSION = (DESKTOP / "VERSION").read_text(encoding="utf-8").strip()

PBS_TAG, PY_VERSION = "20260924", "3.12.14"
PBS_URL = "https://github.com/astral-sh/python-build-standalone/releases/download/" + PBS_TAG
LLAMA_TAG = "b11201"
LLAMA_URL = "https://github.com/ggml-org/llama.cpp/releases/download/" + LLAMA_TAG
PYWEBVIEW = "pywebview==6.2.1"
CERTIFI = "certifi==2026.7.22"

TARGETS = {
    "windows-x64": {"pbs": "x86_64-pc-windows-msvc", "llama": {"cpu": "win-cpu-x64.zip", "vulkan": "win-vulkan-x64.zip"}},
    "macos-arm64": {"pbs": "aarch64-apple-darwin", "llama": {"metal": "macos-arm64.tar.gz"}},
    "linux-x64": {"pbs": "x86_64-unknown-linux-gnu", "llama": {"cpu": "ubuntu-x64.tar.gz", "vulkan": "ubuntu-vulkan-x64.tar.gz"}},
}
# SHA-256 of every download. A file not listed here is checked against the digest GitHub publishes for the
# release asset, and its hash is printed so it can be pinned here.
PINNED: dict[str, str] = {}
APP_FILES = ["desktop.py", "live_check.py", "cynqra", "ui", "scenarios"]
VC_RUNTIME = ("msvcp140", "vcruntime140", "concrt140", "vcomp140", "libomp140")


def log(*a) -> None:
    print("[build]", *a, flush=True)


def fetch(url: str, dest: Path) -> Path:
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    log("download", url)
    req = urllib.request.Request(url, headers={"User-Agent": "cynqra-build"})
    with urllib.request.urlopen(req, timeout=300) as r, open(str(dest) + ".part", "wb") as out:
        shutil.copyfileobj(r, out, 1 << 20)
    Path(str(dest) + ".part").replace(dest)
    return dest


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def github_digest(repo: str, tag: str, name: str) -> str:
    """The SHA-256 GitHub publishes for a release asset."""
    headers = {"User-Agent": "cynqra-build", "Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/tags/{tag}", headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        rel = json.loads(r.read())
    for a in rel["assets"]:
        if a["name"] == name:
            d = a.get("digest") or ""
            if d.startswith("sha256:"):
                return d[7:]
    raise SystemExit(f"GitHub publishes no SHA-256 for {name} in {repo} {tag}; pin it in PINNED")


def verified(url: str, cache: Path, expected: str | None) -> Path:
    path = fetch(url, cache / url.rsplit("/", 1)[1])
    got = sha256(path)
    want = PINNED.get(path.name) or expected
    if got != want:
        path.unlink()
        raise SystemExit(f"{path.name}: SHA-256 {got} does not match {want}")
    log(f"verified {path.name} sha256 {got}")
    return path


def extract(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            z.extractall(dest)
    else:
        with tarfile.open(archive) as t:
            t.extractall(dest, filter="tar") if hasattr(tarfile, "data_filter") else t.extractall(dest)


def pe_imports(path: Path) -> list[str]:
    """The DLL names a Windows executable or DLL imports, read from its PE import table."""
    data = path.read_bytes()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec, opt_size = struct.unpack_from("<H", data, pe + 6)[0], struct.unpack_from("<H", data, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    dirs = opt + (112 if magic == 0x20B else 96)
    imp_rva = struct.unpack_from("<I", data, dirs + 8)[0]
    secs = [struct.unpack_from("<8sIIII", data, opt + opt_size + 40 * i) for i in range(nsec)]

    def off(rva: int) -> int:
        for _, vsize, vaddr, rsize, raw in secs:
            if vaddr <= rva < vaddr + max(vsize, rsize):
                return rva - vaddr + raw
        raise ValueError("rva outside sections")
    names, p = [], off(imp_rva) if imp_rva else None
    while p is not None:
        name_rva = struct.unpack_from("<I", data, p + 12)[0]
        if not name_rva:
            break
        s = off(name_rva)
        names.append(data[s:data.index(b"\0", s)].decode())
        p += 20
    return names


def add_llama(target: str, stage: Path, cache: Path) -> None:
    for accel, suffix in TARGETS[target]["llama"].items():
        name = f"llama-{LLAMA_TAG}-bin-{suffix}"
        archive = verified(f"{LLAMA_URL}/{name}", cache, PINNED.get(name) or github_digest("ggml-org/llama.cpp", LLAMA_TAG, name))
        tmp = cache / f"x_{accel}"
        shutil.rmtree(tmp, ignore_errors=True)
        extract(archive, tmp)
        exe = "llama-server.exe" if target.startswith("windows") else "llama-server"
        found = [p for p in tmp.rglob(exe) if p.is_file()]
        if not found:
            raise SystemExit(f"{name} has no {exe}")
        src, dest = found[0].parent, stage / "llama" / accel
        dest.mkdir(parents=True, exist_ok=True)
        for f in src.iterdir():
            tool = "-impl." in f.name and "server" not in f.name  # llama-bench, llama-cli and the other tools' code
            keep = not tool and (f.name.startswith("llama-server") or f.suffix in (".dll", ".dylib", ".metal")
                                 or ".so" in f.name or f.name.upper().startswith("LICENSE"))
            if keep and (f.is_file() or f.is_symlink()):
                shutil.copy2(f, dest / f.name, follow_symlinks=False)
        if target.startswith("windows"):
            add_vc_runtime(dest)
        log(f"llama-server {accel}: {sorted(p.name for p in dest.iterdir())}")


def add_vc_runtime(folder: Path) -> None:
    """Copy the Visual C++ runtime DLLs llama-server imports into its folder (app-local deployment), so it
    starts on a Windows machine that never installed the Visual C++ Redistributable."""
    sys32 = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32"
    todo = [p for p in folder.iterdir() if p.suffix.lower() in (".exe", ".dll")]
    seen = set()
    while todo:
        p = todo.pop()
        for dll in pe_imports(p):
            low = dll.lower()
            if low in seen or not low.startswith(VC_RUNTIME):
                continue
            seen.add(low)
            if not (folder / dll).exists():
                src = sys32 / dll
                if not src.exists():
                    raise SystemExit(f"{p.name} needs {dll}, which is not in System32 on the build machine")
                shutil.copy2(src, folder / dll)
                log(f"added {dll} for {p.name}")
                todo.append(folder / dll)


def add_python(target: str, stage: Path, cache: Path) -> Path:
    name = f"cpython-{PY_VERSION}+{PBS_TAG}-{TARGETS[target]['pbs']}-install_only_stripped.tar.gz"
    try:
        sums = fetch(f"{PBS_URL}/SHA256SUMS", cache / f"SHA256SUMS-{PBS_TAG}").read_text().split("\n")
        want = next((ln.split()[0] for ln in sums if ln.strip().endswith(name)), None)
    except OSError:
        want = None
    want = want or github_digest("astral-sh/python-build-standalone", PBS_TAG, name)
    archive = verified(f"{PBS_URL}/{name.replace('+', '%2B')}", cache, want)
    extract(archive, stage)  # the archive holds python/
    py = stage / "python" / ("python.exe" if target.startswith("windows") else "bin/python3")
    if not py.exists():
        raise SystemExit(f"no interpreter at {py}")
    # What the app never uses: the Tk GUI toolkit and the IDLE editor built on it.
    lib = stage / "python" / ("Lib" if target.startswith("windows") else "lib/python3.12")
    for name in ("idlelib", "tkinter", "turtledemo", "turtle.py"):
        target_path = lib / name
        shutil.rmtree(target_path, ignore_errors=True) if target_path.is_dir() else target_path.unlink(missing_ok=True)
    for pattern in ("tcl*", "tk*", "itcl*", "libtcl*", "libtk*", "_tkinter*"):
        for p in list((stage / "python").glob(pattern)) + list((stage / "python" / "lib").glob(pattern)) + \
                list((stage / "python" / "DLLs").glob(pattern)) + list((lib / "lib-dynload").glob(pattern)):
            shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
    return py


def add_app(stage: Path, py: Path) -> None:
    app = stage / "app"
    for name in APP_FILES:
        src = ROOT / "poc" / name
        if src.is_dir():
            shutil.copytree(src, app / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            app.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, app / name)
    (app / "VERSION").write_text(VERSION + "\n", encoding="utf-8")
    # unchecked-hash: the compiled files stay valid when copying the app changes the sources' timestamps
    subprocess.run([str(py), "-m", "compileall", "-q", "--invalidation-mode", "unchecked-hash", str(app),
                    str(stage / "python" / "lib")], check=False)


def stage_for(target: str, cache: Path) -> tuple[Path, Path]:
    stage = ROOT / "dist" / "stage" / target / "Cynqra"
    shutil.rmtree(stage.parent, ignore_errors=True)
    stage.mkdir(parents=True)
    py = add_python(target, stage, cache)
    add_llama(target, stage, cache)
    extra = [CERTIFI] + ([PYWEBVIEW] if target.startswith("macos") else [])
    subprocess.run([str(py), "-m", "pip", "install", "--disable-pip-version-check", "--no-warn-script-location", *extra],
                   check=True)
    add_app(stage, py)
    shutil.copy2(DESKTOP / "icon" / "cynqra.png", stage / "cynqra.png")
    return stage, py


# ------------------------------------------------------------------------------------ packages --
def package_windows(stage: Path) -> Path:
    shutil.copy2(DESKTOP / "icon" / "cynqra.ico", stage / "cynqra.ico")
    (stage / "cynqra.cmd").write_text('@"%~dp0python\\python.exe" -X utf8 "%~dp0app\\desktop.py" %*\r\n', encoding="ascii")
    iscc = shutil.which("iscc") or r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    out = ROOT / "dist"
    subprocess.run([iscc, f"/DAppVersion={VERSION}", f"/DSourceDir={stage}", f"/DOutputDir={out}",
                    f"/DIconFile={DESKTOP / 'icon' / 'cynqra.ico'}", str(DESKTOP / "windows" / "cynqra.iss")], check=True)
    return out / f"Cynqra-Setup-{VERSION}-windows-x64.exe"


def magic(p: Path) -> bytes:
    with open(p, "rb") as f:
        return f.read(4)


def package_macos(stage: Path, target: str) -> Path:
    app = stage.parent / "Cynqra.app"
    res = app / "Contents" / "Resources"
    res.mkdir(parents=True)
    for part in ("python", "llama", "app"):
        shutil.move(str(stage / part), str(res / part))
    shutil.copy2(DESKTOP / "icon" / "cynqra.icns", res / "cynqra.icns")
    macos = app / "Contents" / "MacOS"
    macos.mkdir()
    launcher = macos / "Cynqra"
    launcher.write_text(
        "#!/bin/bash\n"
        "# Cynqra: start the app with the Python and llama-server inside this bundle.\n"
        'RES="$(cd "$(dirname "$0")/../Resources" && pwd)"\n'
        "# A downloaded app is quarantined; once you have opened it, its own helpers need not be asked about again.\n"
        'xattr -dr com.apple.quarantine "$RES/llama" "$RES/python" 2>/dev/null\n'
        "export PYTHONDONTWRITEBYTECODE=1\n"
        'exec "$RES/python/bin/python3" -X utf8 "$RES/app/desktop.py" "$@"\n', encoding="utf-8")
    launcher.chmod(0o755)
    with open(app / "Contents" / "Info.plist", "wb") as f:
        plistlib.dump({"CFBundleName": "Cynqra", "CFBundleDisplayName": "Cynqra", "CFBundleIdentifier": "com.cynqra.desktop",
                       "CFBundleVersion": VERSION, "CFBundleShortVersionString": VERSION, "CFBundleExecutable": "Cynqra",
                       "CFBundleIconFile": "cynqra.icns", "CFBundlePackageType": "APPL", "LSMinimumSystemVersion": "12.0",
                       "NSHighResolutionCapable": True, "LSApplicationCategoryType": "public.app-category.developer-tools"}, f)
    # Ad-hoc signature: every Mach-O file first, then the bundle. There is no Apple Developer ID here, so
    # macOS asks once before the first launch (LAPTOP_SETUP.md says how to allow it).
    machos = [p for p in app.rglob("*") if p.is_file() and not p.is_symlink() and magic(p) in (
        b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf")]
    for p in machos:
        subprocess.run(["codesign", "--force", "--sign", "-", "--timestamp=none", str(p)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["codesign", "--force", "--sign", "-", "--timestamp=none", str(app)], check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
    log(f"signed {len(machos)} Mach-O files and the bundle (ad hoc)")
    root = stage.parent / "dmg"
    root.mkdir()
    shutil.move(str(app), str(root / "Cynqra.app"))
    (root / "Applications").symlink_to("/Applications")
    out = ROOT / "dist" / f"Cynqra-{VERSION}-macos-arm64.dmg"
    subprocess.run(["hdiutil", "create", "-volname", "Cynqra", "-srcfolder", str(root), "-ov", "-format", "UDZO",
                    str(out)], check=True)
    return out


def package_linux(stage: Path) -> Path:
    launcher = stage / "cynqra"
    launcher.write_text('#!/bin/sh\n# Cynqra: start the app with the Python and llama-server in this folder.\n'
                        'HERE="$(dirname "$(readlink -f "$0")")"\n'
                        'exec "$HERE/python/bin/python3" -X utf8 "$HERE/app/desktop.py" "$@"\n', encoding="utf-8")
    launcher.chmod(0o755)
    shutil.copy2(DESKTOP / "linux" / "install.sh", stage / "install.sh")
    (stage / "install.sh").chmod(0o755)
    out = ROOT / "dist" / f"Cynqra-{VERSION}-linux-x64.tar.gz"
    with tarfile.open(out, "w:gz") as t:
        t.add(stage, arcname="Cynqra")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--target", required=True, choices=sorted(TARGETS))
    ap.add_argument("--stage-only", action="store_true", help="assemble dist/stage/<target>/Cynqra, do not package")
    args = ap.parse_args()
    cache = ROOT / "dist" / "cache"
    stage, py = stage_for(args.target, cache)
    subprocess.run([str(py), "--version"], check=True)
    if args.stage_only:
        log("staged at", stage)
        return 0
    out = {"windows-x64": package_windows, "linux-x64": package_linux}.get(args.target)
    out = out(stage) if out else package_macos(stage, args.target)
    log(f"built {out.name}: {out.stat().st_size / 1e6:.0f} MB, sha256 {sha256(out)}")
    (ROOT / "dist" / (out.name + ".sha256")).write_text(f"{sha256(out)}  {out.name}\n", encoding="ascii")
    return 0


if __name__ == "__main__":
    sys.exit(main())
