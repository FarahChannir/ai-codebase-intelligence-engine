from pathlib import Path
import zipfile
import tempfile
import pathspec
import subprocess
import os

##### this will conatin this Steps: 
#walk_files  and 
#handle_zip_upload
#filter_files

### function that takes a root path and returns every file in it, including files in subdirectories
def walk_files(root: str) -> list[str]:
    root_path = Path(root)
    return [str(p) for p in root_path.rglob("*") if p.is_file()]






ALWAYS_IGNORE_EXTENSIONS = {
    ".meta", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico",
    ".fbx", ".wav", ".mp3", ".psd", ".ttf", ".otf",
    ".dll", ".pdb", ".exe", ".so", ".dylib", ".cache",".gitignore",".vsconfig", ".utmp"
}
ALWAYS_IGNORE_DIRS = {
    "obj", "bin", ".git", "node_modules", ".vs", "__pycache__",
    "dist", "build", ".idea", "Library", "Temp", "Logs", "ProjectSettings",
    ".utmp",
}

def load_gitignore_spec(repo_root: Path) -> pathspec.PathSpec | None:
    """
    Loads .gitignore if present. Returns None if missing or unreadable —
    callers must treat None as 'no extra filtering, rely on hardcoded rules.'
    """
    gitignore_path = repo_root / ".gitignore"
    if not gitignore_path.exists():
        return None
    try:
        lines = gitignore_path.read_text(encoding="utf-8").splitlines()
        return pathspec.PathSpec.from_lines("gitwildmatch", lines)
    except Exception:
        # a malformed .gitignore should never break ingestion
        return None
    

# filter_files applies a series of filters to the list of files, returning only those that should be kept
def filter_files(files: list[str], repo_root: str) -> list[str]:
    repo_root_path = Path(repo_root)
    spec = load_gitignore_spec(repo_root_path)

    filtered = []

    for file in files:
        file_path = Path(file)

        try:
            relative_path = file_path.relative_to(repo_root_path)
        except ValueError:
            continue

        relative_str = relative_path.as_posix()

        # 1. hardcoded directory check — primary defense, always applies
        if any(part in ALWAYS_IGNORE_DIRS for part in relative_path.parts):
            continue

        # 2. hardcoded extension check — primary defense, always applies
        if file_path.suffix.lower() in ALWAYS_IGNORE_EXTENSIONS:
            continue

        # 3. gitignore — secondary, optional layer, only if it loaded cleanly
        if spec and spec.match_file(relative_str):
            continue

        filtered.append(file)

    return filtered



#zip-upload path is a thin wrapper that just extracts first
def handle_zip_upload(zip_path: str) -> str:
    dest = tempfile.mkdtemp()
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest)
    return dest



#  Language detector
EXT_TO_LANGUAGE = {
    ".py": "python",
    ".cs": "csharp",
    ".razor": "razor",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".java": "java",
    ".go": "go",
    ".rb": "ruby",
    ".rs": "rust",
    ".html": "html",
    ".css": "css",
    ".cpp": "cpp",
    ".c": "c",
    ".shader": "hlsl",
    ".cginc": "hlsl",
}

def detect_language(file_path: str) -> str | None:
    """
    file_path: a path from the filtered file list
    returns: a language tag (e.g. "csharp", "python") or None if unrecognized
    """
    ext = Path(file_path).suffix.lower()
    return EXT_TO_LANGUAGE.get(ext)



# def clone_repo(url: str, branch: str | None = None) -> str:
#     dest = tempfile.mkdtemp()
#     cmd = ["git", "clone", "--depth", "1"]
#     if branch:
#         cmd += ["--branch", branch]
#     cmd += [url, dest]
#     print(f"cloning {url} branch={branch or 'default'} into {dest}")
#     subprocess.run(cmd, check=True, capture_output=True)
#     return dest


# def clone_repo(url: str, branch: str | None = None, token: str | None = None) -> str:
#     dest = tempfile.mkdtemp()
    
#     if token and url.startswith("https://"):
#         url = url.replace("https://", f"https://{token}@")
    
#     cmd = ["git", "clone", "--depth", "1"]
#     if branch:
#         cmd += ["--branch", branch]
#     cmd += [url, dest]
    
#     print(f"cloning branch={branch or 'default'} into {dest}")  
#     # note: don't print url here anymore — it now contains the token
#     subprocess.run(cmd, check=True, capture_output=True)
#     return dest


def clone_repo(url: str, branch: str | None = None, token: str | None = None) -> str:
    dest = tempfile.mkdtemp()

    if token and url.startswith("https://"):
        auth_url = url.replace("https://", f"https://{token}@")
    else:
        auth_url = url

    cmd = ["git", "-c", "credential.helper=", "clone", "--depth", "1"]
    if branch:
        cmd += ["--branch", branch]
    cmd += [auth_url, dest]

    print(f"cloning {url} branch={branch or 'default'} into {dest}")

    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        )
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode(errors="replace")
        raise RuntimeError(f"git clone failed for {url!r}: {stderr}") from None

    return dest