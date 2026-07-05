from __future__ import annotations

import os
import subprocess
import tempfile
import zipfile
from pathlib import Path

import pathspec


# across the ecosystems this engine targets (.NET, Unity, JS, Python).
ALWAYS_IGNORE_DIRS: set[str] = {
    # .NET / Visual Studio
    "obj", "bin", ".vs",
    # JavaScript / Node
    "node_modules", "dist", "build",
    # Python
    "__pycache__",
    # Git
    ".git",
    # JetBrains IDEs
    ".idea",
    # Unity (generated, never hand-authored)
    "Library", "Temp", "Logs", "ProjectSettings", ".utmp",
}

# File extensions that are never source code.
# Binary assets, compiled outputs, and IDE metadata files.
ALWAYS_IGNORE_EXTENSIONS: set[str] = {
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".tif", ".tiff", ".exr", ".psd",
    # Audio / 3D
    ".wav", ".mp3", ".fbx", ".anim",
    # Fonts
    ".ttf", ".otf",
    # Compiled outputs
    ".dll", ".pdb", ".exe", ".so", ".dylib",
    # IDE / tooling metadata
    ".meta", ".cache", ".user", ".suo",
    # Config files that are not source code
    ".vsconfig",
}


# parsing layer treats as "skip this file."
EXT_TO_LANGUAGE: dict[str, str] = {
    # Web
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".html": "html",
    ".css": "css",
    # .NET
    ".cs": "csharp",
    ".razor": "razor",          # kept separate from csharp — needs different parser
    # Systems
    ".cpp": "cpp",
    ".c": "c",
    ".rs": "rust",
    ".go": "go",
    # JVM
    ".java": "java",
    ".rb": "ruby",
    # Scripting
    ".py": "python",
    # GPU / shaders (Unity ShaderLab + HLSL includes)
    ".shader": "hlsl",
    ".cginc": "hlsl",
}


# ---------------------------------------------------------------------------
# File system reader
# ---------------------------------------------------------------------------

def walk_files(root: str) -> list[str]:
    """
   
        List of absolute file path strings, in filesystem order.
    """
    root_path = Path(root)
    return [str(p) for p in root_path.rglob("*") if p.is_file()]


def handle_zip_upload(zip_path: str) -> str:
    """
   
        zip_path: Absolute path to the zip file to extract.

    Returns:
        Absolute path to the temporary directory containing extracted files.

    Raises:
        zipfile.BadZipFile: If the file is not a valid zip archive.
    """
    dest = tempfile.mkdtemp()
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest)
    return dest


# ---------------------------------------------------------------------------
# File filter
# ---------------------------------------------------------------------------

def _load_gitignore_spec(repo_root: Path) -> pathspec.PathSpec | None:
    """
    Load and parse the .gitignore at *repo_root*, if present.

    Returns None if the file does not exist or cannot be parsed — callers
    must treat None as "no gitignore filtering, rely on hardcoded rules."
    A malformed or missing .gitignore must never break ingestion.

    Args:
        repo_root: Root directory of the repository.

    Returns:
        Parsed PathSpec, or None.
    """
    gitignore_path = repo_root / ".gitignore"
    if not gitignore_path.exists():
        return None
    try:
        lines = gitignore_path.read_text(encoding="utf-8").splitlines()
        return pathspec.PathSpec.from_lines("gitwildmatch", lines)
    except Exception:
        return None


def filter_files(files: list[str], repo_root: str) -> list[str]:
    """
    Remove non-source files from *files*, returning only indexable code.

    Three-stage filtering, applied in priority order:

    1. Hardcoded directory deny-list (ALWAYS_IGNORE_DIRS) — removes build
       artifacts, dependency caches, and IDE folders. Primary defense;
       always applies regardless of .gitignore presence.

    2. Hardcoded extension deny-list (ALWAYS_IGNORE_EXTENSIONS) — removes
       binary assets, compiled outputs, and metadata files. Primary defense;
       always applies regardless of .gitignore presence.

    3. .gitignore patterns — optional secondary layer for project-specific
       exclusions. Silently skipped if .gitignore is absent or malformed,
       since many enterprise repos lack it or have incomplete versions.

    Args:
        files: Raw file list from walk_files.
        repo_root: Repository root used to resolve relative paths and
                   locate the .gitignore file.

    Returns:
        Filtered list containing only files that pass all three stages.
    """
    repo_root_path = Path(repo_root)
    spec = _load_gitignore_spec(repo_root_path)
    filtered = []

    for file in files:
        file_path = Path(file)

        try:
            relative_path = file_path.relative_to(repo_root_path)
        except ValueError:
            # File is outside repo_root — skip silently
            continue

        # Stage 1: directory deny-list
        if any(part in ALWAYS_IGNORE_DIRS for part in relative_path.parts):
            continue

        # Stage 2: extension deny-list
        if file_path.suffix.lower() in ALWAYS_IGNORE_EXTENSIONS:
            continue

        # Stage 3: .gitignore (optional)
        if spec and spec.match_file(relative_path.as_posix()):
            continue

        filtered.append(file)

    return filtered


# ---------------------------------------------------------------------------
# Language detector
# ---------------------------------------------------------------------------

def detect_language(file_path: str) -> str | None:
    """
    Return the programming language tag for *file_path*, or None.

    Detection is extension-based. This covers the vast majority of real
    codebases without the complexity or fragility of content-based detection.
    Files with unrecognized extensions return None and are skipped by the
    parsing layer.

    Note: .razor is intentionally kept separate from csharp — Razor files
    require a different parsing strategy (interleaved HTML and @code blocks)
    and must not be confused with plain C# files.

    Args:
        file_path: Absolute or relative path to the file.

    Returns:
        Language tag string (e.g. "csharp", "python"), or None if the
        extension is not in EXT_TO_LANGUAGE.
    """
    ext = Path(file_path).suffix.lower()
    return EXT_TO_LANGUAGE.get(ext)


# ---------------------------------------------------------------------------
# Git connector
# ---------------------------------------------------------------------------

def clone_repo(
    url: str,
    branch: str | None = None,
    token: str | None = None,
) -> str:
    """
    Shallow-clone a git repository to a temporary directory.

    Supports public and private repositories over HTTPS. Private repo
    authentication uses token injection into the URL, which is compatible
    with GitHub, GitLab, and Azure DevOps personal access tokens.

    SSH is not supported in v1 — it requires managing SSH agents and keys,
    which adds complexity not justified for the initial release.

    The returned path feeds directly into walk_files, making the git clone
    path identical to the local folder and zip paths from that point on.
    The caller is responsible for cleaning up the temporary directory.

    Args:
        url: HTTPS git URL (e.g. "https://github.com/user/repo.git").
        branch: Branch to clone. Defaults to the repository's default branch.
        token: Personal access token for private repository authentication.
               Never logged or included in exception messages.

    Returns:
        Absolute path to the temporary directory containing the cloned repo.

    Raises:
        RuntimeError: If the clone fails for any reason (bad URL, auth
                      failure, branch not found, network error). The token
                      is never included in the error message.
    """
    dest = tempfile.mkdtemp()

    # Inject token into URL for private repo auth.
    # auth_url is kept separate from url so the token never appears in logs.
    if token and url.startswith("https://"):
        auth_url = url.replace("https://", f"https://{token}@")
    else:
        auth_url = url

    # credential.helper= disables Windows Credential Manager and all other
    # credential helpers, preventing interactive prompts in server contexts.
    cmd = ["git", "-c", "credential.helper=", "clone", "--depth", "1"]
    if branch:
        cmd += ["--branch", branch]
    cmd += [auth_url, dest]

    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            # GIT_TERMINAL_PROMPT=0 ensures git never prompts for credentials.
            # Combined with credential.helper= above, any auth failure is
            # immediate rather than hanging indefinitely.
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode(errors="replace")
        # Raise a clean error — the original CalledProcessError is discarded
        # (from None) because its .cmd attribute contains the token-injected URL.
        raise RuntimeError(f"git clone failed for {url!r}: {stderr}") from None

    return dest




#--------------------------------------------------------------------------

from dataclasses import dataclass
from typing import Optional
from pathlib import Path

@dataclass
class FileRecord:
    path: str           # absolute path — used to actually read the file
    relative_path: str  # relative to repo root — used for display and citations
    language: str
    source: str





def ingest(
    source: str,
    source_type: str,
    branch: Optional[str] = None,
    token: Optional[str] = None
) -> list[FileRecord]:

    if source_type == "git":
        local_path = clone_repo(source, branch, token)
    elif source_type == "zip":
        local_path = handle_zip_upload(source)
    elif source_type == "folder":
        local_path = source
    else:
        raise ValueError(f"Unknown source type: {source_type}")

    files = walk_files(local_path)
    filtered = filter_files(files, local_path)

    records = []

    for file_path in filtered:
        language = detect_language(file_path)
        if language is not None:
            records.append(
                FileRecord(
                    path=file_path,
                    relative_path=str(Path(file_path).relative_to(local_path)),
                    language=language,
                    source=source,
                )
            )

    return records