

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

def extract_python_chunks(source_code: str, file_path: str, relative_path: str, source: str) -> list[CodeChunk]:
    parser = get_python_parser()
    tree = parser.parse(source_code.encode("utf-8"))
    root = tree.root_node

    chunks: list[CodeChunk] = []
    source_lines = source_code.splitlines()

    def get_node_name(node) -> str:
        for child in node.children:
            if child.type == "identifier":
                return child.text.decode("utf-8")
        return "<unknown>"

    def get_node_text(node) -> str:
        return "\n".join(source_lines[node.start_point[0]: node.end_point[0] + 1])

    def walk(node):
        if node.type == "function_definition":
            chunks.append(CodeChunk(
                file_path=file_path,
                relative_path=relative_path,
                language="python",
                source=source,
                content=get_node_text(node),
                chunk_type="function",
                name=get_node_name(node),
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
            ))
        elif node.type == "class_definition":
            chunks.append(CodeChunk(
                file_path=file_path,
                relative_path=relative_path,
                language="python",
                source=source,
                content=get_node_text(node),
                chunk_type="class",
                name=get_node_name(node),
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
            ))

        for child in node.children:
            walk(child)

    walk(root)
    return chunks

if __name__ == "__main__":
    sample_code = """def add(a, b):
    return a + b

class Calculator:
    def multiply(self, a, b):
        return a * b
"""
    chunks = extract_python_chunks(sample_code, "test.py", "test.py", "local")
    for c in chunks:
        print(f"{c.chunk_type}: {c.name} (lines {c.start_line}-{c.end_line})")

########## output ##########
#function: add (lines 1-3)
#class: Calculator (lines 5-8)
#function: multiply (lines 6-8)