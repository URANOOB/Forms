"""Prepare an allowlisted Worker artifact; never copy secrets or uploaded files."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".cloudflare"


def copy_file(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def include_dependency(path):
    parts = path.parts
    if path.suffix in (".pyc", ".c", ".h", ".po"):
        return False
    if "__pycache__" in parts or "static" in parts:
        return False
    if "locale" in parts and path.suffix != ".py":
        index = parts.index("locale")
        if len(parts) > index + 2 and parts[index + 1] not in ("es", "en"):
            return False
    if parts[:2] == ("botocore", "data") and len(parts) > 3 and parts[2] != "s3":
        return False
    return parts[:2] != ("Crypto", "SelfTest")


def main():
    # Work on generated files only. Removing individual old files avoids stale
    # Python modules after a source rename and never traverses a symlink.
    for folder in (OUTPUT / "src", OUTPUT / "assets"):
        if folder.is_symlink() or folder.resolve() != folder.absolute():
            raise RuntimeError("Build directory must not be a symlink")
        if folder.exists():
            for path in folder.rglob("*"):
                if path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()):
                    raise RuntimeError("Unexpected path in generated output")
                if path.is_file():
                    path.unlink()

    # Keep uv's Pyodide interpreter and build environment on the same volume.
    # Its Windows launcher cannot inspect an interpreter across drive letters.
    with tempfile.TemporaryDirectory(prefix="forms-worker-build-") as temporary:
        staging = Path(temporary)
        for name in ("pyproject.toml", "pylock.toml", "wrangler.jsonc"):
            copy_file(ROOT / name, staging / name)
        subprocess.run(
            [
                "uv",
                "tool",
                "run",
                "--with",
                "uv==0.12.3",
                "--from",
                "workers-py==1.17.4",
                "pywrangler",
                "sync",
            ],
            cwd=staging,
            env={
                k: v
                for k, v in os.environ.items()
                if k not in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "UV_PYTHON_INSTALL_DIR")
            },
            check=True,
        )
        vendor = ROOT / "python_modules"
        if vendor.is_symlink():
            raise RuntimeError("Vendor directory must not be a symlink")
        for path in vendor.rglob("*"):
            if path.is_symlink() or not path.resolve().is_relative_to(vendor.resolve()):
                raise RuntimeError("Unexpected vendor path")
            if path.is_file():
                path.unlink()
        dependencies = staging / "python_modules"
        for source in dependencies.rglob("*"):
            relative = source.relative_to(dependencies)
            if source.is_file() and include_dependency(relative):
                copy_file(source, vendor / relative)
        # Pyodide 3.14 returns JsNull, not None, for HEAD/204 response bodies.
        # urllib3 2.6's identity check otherwise tries getReader() on null.
        fetch = vendor / "urllib3/contrib/emscripten/fetch.py"
        original = "if response_js.body is not None:"
        source = fetch.read_text(encoding="utf-8")
        if source.count(original) != 1:
            raise RuntimeError("Review urllib3 null-body compatibility after dependency update")
        fetch.write_text(source.replace(original, "if response_js.body:"), encoding="utf-8")
    for name in ("apps", "config", "templates"):
        for source in (ROOT / name).rglob("*"):
            if source.is_symlink():
                raise RuntimeError("Source symlinks are not supported")
            if not source.is_file() or source.suffix not in (".py", ".html"):
                continue
            if "tests" in source.relative_to(ROOT).parts or "__pycache__" in source.parts:
                continue
            copy_file(source, OUTPUT / "src" / source.relative_to(ROOT))
    copy_file(ROOT / "deployment/cloudflare_entry.py", OUTPUT / "src/entry.py")

    # collectstatic needs settings but must not access the production services.
    build_env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.production",
        "DJANGO_SECRET_KEY": "build-only-key-not-used-for-any-runtime-session-0123456789",
        "DATABASE_URL": "postgresql://build:build@127.0.0.1/build",
        "DJANGO_ALLOWED_HOSTS": "build.invalid",
        "FILE_STORAGE": "local",
    }
    subprocess.run(
        ["uv", "run", "--locked", "python", "manage.py", "collectstatic", "--noinput"],
        cwd=ROOT,
        env=build_env,
        check=True,
    )
    for source in (ROOT / "staticfiles").rglob("*"):
        if source.is_file() and not source.is_symlink():
            copy_file(source, OUTPUT / "assets/static" / source.relative_to(ROOT / "staticfiles"))
    print("Worker source and static assets prepared; private files excluded.")


if __name__ == "__main__":
    main()
