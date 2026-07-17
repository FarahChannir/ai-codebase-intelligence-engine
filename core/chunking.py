

from __future__ import annotations

from dataclasses import dataclass

from tree_sitter import Language, Parser
import tree_sitter_python as tspython

@dataclass
class CodeChunk:
    # Where it came from
    file_path: str        # absolute path to the file
    relative_path: str    # e.g. "src/GameManager.cs"
    language: str         # "csharp", "python", "javascript", "typescript"
    source: str           # repo URL or folder path

    # What it is
    content: str          # the actual code text of this chunk
    chunk_type: str       # "function", "class", "method", "module"
    name: str             # e.g. "Respawn", "GameManager", "AudioManager"
    start_line: int       # line where this chunk starts in the file
    end_line: int         # line where it ends


def get_python_parser() -> Parser:
    PY_LANGUAGE = Language(tspython.language())
    parser = Parser(PY_LANGUAGE)
    return parser


get_python_parser()


if __name__ == "__main__":
    parser = get_python_parser()

    sample_code = b"""
def add(a, b):
    return a + b

class Calculator:
    def multiply(self, a, b):
        return a * b
"""

    tree = parser.parse(sample_code)
    print(tree.root_node)