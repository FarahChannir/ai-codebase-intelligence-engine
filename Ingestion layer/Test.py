from pathlib import Path

from matplotlib import lines
from ingestion import handle_zip_upload, walk_files, filter_files

repo_root = r"C:\Kabbani\boardgames"
files = []

files = walk_files(repo_root)

# Checkpoint 1: does the raw OS-level directory listing even show BoardGameWebApp?
print("--- top-level folders seen by Path ---")
for p in Path(repo_root).iterdir():
    if p.is_file():
        if p.suffix.lower() == ".zip" or p.suffix.lower() == ".rar":
            print(f"Found zip file: {p.name}")
            zip_dest = handle_zip_upload(str(p))
            files += walk_files(zip_dest)


filtered = filter_files(files, repo_root)


with open("filter_files.txt", "w", encoding="utf-8") as file:
    file.write("\n".join(filtered))

print(Path("filter_files.txt").resolve())

    