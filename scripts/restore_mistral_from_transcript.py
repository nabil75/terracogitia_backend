"""Restore mistral/*.py from Cursor agent transcript ApplyPatch history."""
import json
import re
from pathlib import Path

TRANSCRIPT = Path(
    r"C:\Users\LG\.cursor\projects\c-Users-LG-OneDrive-Documents-Travail-angular-projects-terracogitia-frontend"
    r"\agent-transcripts\7444897f-6535-47c2-b14b-df62c74c8e51\7444897f-6535-47c2-b14b-df62c74c8e51.jsonl"
)
BASE = Path(__file__).resolve().parent.parent / "mistral"


def parse_add_file(patch_text: str) -> str | None:
    m = re.search(
        r"\*\*\* Add File: [^\n]+\n((?:\+[^\n]*\n)+)",
        patch_text,
    )
    if not m:
        return None
    return "\n".join(line[1:] for line in m.group(1).splitlines()) + "\n"


def parse_patch(patch_text: str):
    lines = patch_text.splitlines()
    file_path = None
    hunks = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("*** Add File:") or line.startswith("*** Update File:"):
            file_path = line.split(":", 1)[1].strip()
            i += 1
            continue
        if line.startswith("@@"):
            hunk_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith("@@") and not lines[i].startswith(
                "*** "
            ):
                hunk_lines.append(lines[i])
                i += 1
            hunks.append(hunk_lines)
            continue
        if line.startswith("*** End Patch"):
            break
        i += 1
    return file_path, hunks


def apply_hunk(content_lines: list[str], hunk_lines: list[str]) -> list[str]:
    old, new = [], []
    for ln in hunk_lines:
        if not ln:
            old.append("")
            new.append("")
        elif ln[0] == " ":
            old.append(ln[1:])
            new.append(ln[1:])
        elif ln[0] == "-":
            old.append(ln[1:])
        elif ln[0] == "+":
            new.append(ln[1:])
    olen = len(old)
    for start in range(len(content_lines) + 1):
        if start + olen > len(content_lines):
            break
        if content_lines[start : start + olen] == old:
            return content_lines[:start] + new + content_lines[start + olen :]
    raise ValueError("hunk not found: " + repr(old[:2]))


def main():
    files: dict[str, str] = {}
    with TRANSCRIPT.open(encoding="utf-8") as f:
        for line in f:
            o = json.loads(line)
            if o.get("role") != "assistant":
                continue
            for part in o.get("message", {}).get("content", []):
                if part.get("type") != "tool_use" or part.get("name") != "ApplyPatch":
                    continue
                patch = part.get("input", "")
                if isinstance(patch, dict):
                    patch = patch.get("patch", "") or str(patch)
                if "mistral" not in patch.replace("\\", "/"):
                    continue
                if "*** Add File:" in patch:
                    fp = patch.split("*** Add File:")[1].split("\n", 1)[0].strip()
                    name = Path(fp.replace("\\", "/")).name
                    body = parse_add_file(patch)
                    if body:
                        files[name] = body
                    continue
                if "*** Update File:" not in patch:
                    continue
                fp, hunks = parse_patch(patch)
                if not fp:
                    continue
                name = Path(fp.replace("\\", "/")).name
                if name not in files:
                    continue
                content_lines = files[name].splitlines()
                for hunk in hunks:
                    try:
                        content_lines = apply_hunk(content_lines, hunk)
                    except ValueError as err:
                        print("WARN", name, err)
                files[name] = "\n".join(content_lines) + ("\n" if content_lines else "")

    BASE.mkdir(parents=True, exist_ok=True)
    for name, content in sorted(files.items()):
        (BASE / name).write_text(content, encoding="utf-8")
        print(f"wrote {name} ({len(content)} bytes)")


if __name__ == "__main__":
    main()
