#!/usr/bin/env python3
"""Prepare, validate and render source-bound, step-by-step code tutorials."""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

try:
    import yaml
    from pygments import lex
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import get_lexer_by_name
    from pygments.lexers.special import TextLexer
    from pygments.util import ClassNotFound
except ImportError as exc:
    raise SystemExit("Missing dependency. Run: python -m pip install -r "
                     + str(Path(__file__).resolve().parents[1] / "requirements.txt")) from exc

PACKAGE = Path(__file__).resolve().parents[1]
ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


class InputError(ValueError):
    """An author-facing input error, with no traceback necessary."""


class UniqueLoader(yaml.SafeLoader):
    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise InputError("YAML aliases are unsupported; use explicit source references.")
        return super().compose_node(parent, index)

    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise InputError("YAML mapping keys must be strings.")
            if key in result:
                raise InputError(f"Duplicate YAML key: {key}")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def read_yaml(path):
    try:
        with Path(path).open(encoding="utf-8-sig") as stream:
            value = yaml.load(stream, Loader=UniqueLoader)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise InputError(f"Cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise InputError(f"{path}: expected a YAML mapping.")
    return value


def mapping(value, where, allowed, required=()):
    if not isinstance(value, dict):
        raise InputError(f"{where}: expected a mapping.")
    unknown = set(value) - set(allowed)
    missing = set(required) - set(value)
    if unknown:
        raise InputError(f"{where}: unknown field(s): {', '.join(sorted(unknown))}")
    if missing:
        raise InputError(f"{where}: missing field(s): {', '.join(sorted(missing))}")


def text(value, where, allow_empty=False):
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise InputError(f"{where}: expected {'a string' if allow_empty else 'nonempty text'}.")
    return value


def identifier(value, where):
    text(value, where)
    if not ID_RE.fullmatch(value):
        raise InputError(f"{where}: use a letter followed by letters, digits, '-' or '_'.")
    return value


def sequence(value, where, nonempty=False):
    if not isinstance(value, list) or (nonempty and not value):
        raise InputError(f"{where}: expected {'a nonempty' if nonempty else 'a'} list.")
    return value


def version(value, where):
    if type(value) is not int or value != 1:
        raise InputError(f"{where}: only version: 1 is supported.")


def load_scope(path):
    raw = read_yaml(path)
    mapping(raw, "scope", {"version", "sources"}, {"version", "sources"})
    version(raw["version"], "scope.version")
    sources, ids, targets = [], set(), set()
    for index, source in enumerate(sequence(raw["sources"], "scope.sources", True)):
        where = f"sources[{index}]"
        mapping(source, where, {"id", "kind", "language", "label", "path", "content"},
                {"id", "kind", "content"})
        sid = identifier(source["id"], where + ".id")
        if sid in ids:
            raise InputError(f"Duplicate source id: {sid}")
        ids.add(sid)
        kind = source["kind"]
        if kind not in ("code", "diff", "context", "history"):
            raise InputError(f"{sid}: kind must be code, diff, context or history.")
        content = text(source["content"], sid + ".content", True)
        if not content:
            raise InputError(f"{sid}: empty source.")
        # A terminal newline terminates the last physical line; it is not another line.
        parts = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if parts[-1] == "":
            parts.pop()
        rows = []
        for number, line in enumerate(parts, 1):
            operation, body = "code", line
            if kind == "diff":
                if not line or line[0] not in " +-":
                    raise InputError(f"{sid}:{number}: diff lines require ' ', '+' or '-' prefix; "
                                     "omit Git/hunk headers. Blank diff lines still need a prefix.")
                if line.startswith(("+++ ", "--- ")):
                    raise InputError(f"{sid}:{number}: omit file headers from diff fragments.")
                operation = {"+": "add", "-": "delete", " ": "context"}[line[0]]
                body = line[1:]
            elif kind in ("context", "history"):
                operation = "context"
            required = kind == "code" or operation in ("add", "delete")
            if required:
                targets.add((sid, number))
            rows.append({"number": number, "text": body, "operation": operation,
                         "required": required})
        sources.append({"id": sid, "kind": kind,
                        "language": text(source.get("language", "text"), sid + ".language"),
                        "label": text(source.get("label", source.get("path", sid)), sid + ".label"),
                        "path": text(source.get("path", ""), sid + ".path", True), "lines": rows})
    if not targets:
        raise InputError("The scope has no required lines. Supply at least one code or changed diff line.")
    canonical = json.dumps({"version": 1, "sources": sources}, ensure_ascii=False,
                           sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return {"digest": digest, "sources": sources, "targets": targets}


def select(value, size, where):
    if value is None:
        return set()
    items = value if isinstance(value, list) else [value]
    result = set()
    for item in items:
        if item in ("all", "*"):
            result.update(range(1, size + 1))
            continue
        if type(item) is int:
            start = end = item
        elif isinstance(item, str) and re.fullmatch(r"[0-9]+(?:-[0-9]+)?", item):
            parts = item.split("-")
            start, end = int(parts[0]), int(parts[-1])
        else:
            raise InputError(f"{where}: use line numbers, inclusive ranges like '3-7', or 'all'.")
        if start < 1 or end < start or end > size:
            raise InputError(f"{where}: range {item} is outside 1-{size}.")
        result.update(range(start, end + 1))
    return result


def safe_url(value):
    if not isinstance(value, str) or not value.strip():
        return False
    if any(ord(c) < 32 for c in value) or "\\" in value:
        return False
    value = value.strip()
    try:
        parsed = urlsplit(value)
        return parsed.scheme.lower() in ("http", "https") or (
            not parsed.scheme and not parsed.netloc and not value.startswith("//"))
    except ValueError:
        return False


INLINE = re.compile(r"`([^`\n]+)`|\*\*([^*\n]+)\*\*|\[([^\]\n]+)\]\(([^\s)]+)\)|\*([^*\n]+)\*")


def inline_markdown(value):
    out, offset = [], 0
    for match in INLINE.finditer(value):
        out.append(html.escape(value[offset:match.start()]))
        code, bold, label, url, emphasis = match.groups()
        if code is not None:
            out.append("<code>" + html.escape(code) + "</code>")
        elif bold is not None:
            out.append("<strong>" + html.escape(bold) + "</strong>")
        elif label is not None:
            if safe_url(url):
                out.append('<a href="' + html.escape(url, quote=True)
                           + '" rel="noopener noreferrer">' + html.escape(label) + "</a>")
            else:
                out.append(html.escape(label))
        else:
            out.append("<em>" + html.escape(emphasis) + "</em>")
        offset = match.end()
    out.append(html.escape(value[offset:]))
    return "".join(out)


def markdown(value):
    """A deliberately small, escaped Markdown subset; code comes from source nodes."""
    if "```" in value or "~~~" in value:
        raise InputError("Use a declared source/code node instead of fenced code in prose, notes or callouts.")
    result = []
    for block in re.split(r"\n\s*\n", value.strip()):
        rows = block.splitlines()
        if not rows:
            continue
        if all(re.match(r"^[-*] ", r) for r in rows):
            result.append("<ul>" + "".join("<li>" + inline_markdown(r[2:]) + "</li>" for r in rows) + "</ul>")
        elif all(re.match(r"^[0-9]+\. ", r) for r in rows):
            result.append("<ol>" + "".join("<li>" + inline_markdown(re.sub(r"^[0-9]+\. ", "", r))
                                         + "</li>" for r in rows) + "</ol>")
        elif all(r.startswith("> ") for r in rows):
            result.append("<blockquote>" + inline_markdown(" ".join(r[2:] for r in rows)) + "</blockquote>")
        elif len(rows) == 1 and rows[0].startswith("### "):
            result.append("<h3>" + inline_markdown(rows[0][4:]) + "</h3>")
        else:
            result.append("<p>" + inline_markdown("\n".join(rows)) + "</p>")
    return "\n".join(result)


def highlight_lines(source):
    rows = source["lines"]
    # Lex the whole snippet so multiline strings and comments keep their token state.
    try:
        lexer = get_lexer_by_name(source["language"], stripnl=False, ensurenl=False)
    except ClassNotFound:
        lexer = TextLexer(stripnl=False, ensurenl=False)
    output, current = ["" for _ in rows], 0
    formatter = HtmlFormatter()
    original = "\n".join(row["text"] for row in rows)
    tokens = list(lex(original, lexer))
    if "".join(value for _, value in tokens) != original:
        return [html.escape(row["text"]) for row in rows]
    for token, value in tokens:
        css = formatter._get_css_class(token)
        for part_index, part in enumerate(value.split("\n")):
            if part_index:
                current += 1
            if current < len(rows) and part:
                escaped = html.escape(part)
                output[current] += f'<span class="{css}">{escaped}</span>' if css else escaped
    return output


def compile_tutorial(scope, raw):
    mapping(raw, "walkthrough", {"version", "mode", "scope_digest", "title", "subtitle",
                                 "intro", "language", "steps"},
            {"version", "mode", "scope_digest", "title", "steps"})
    version(raw["version"], "walkthrough.version")
    if raw["mode"] not in ("authored", "reading"):
        raise InputError("mode must be authored or reading.")
    if raw["scope_digest"] != scope["digest"]:
        raise InputError("Scope digest mismatch. Run prepare on the current scope, recheck line "
                         "references, then use its scope_digest. Existing references are not migrated.")
    if raw["mode"] == "reading" and any(s["kind"] == "history" for s in scope["sources"]):
        raise InputError("reading mode cannot contain history sources. Explain final supplied code only.")
    source_by_id = {s["id"]: s for s in scope["sources"]}
    owners, steps, step_ids = {}, [], set()
    for index, step in enumerate(sequence(raw["steps"], "walkthrough.steps")):
        where = f"steps[{index}]"
        mapping(step, where, {"id", "title", "summary", "content"}, {"id", "title", "content"})
        sid = identifier(step["id"], where + ".id")
        if sid in step_ids:
            raise InputError(f"Duplicate step id: {sid}")
        step_ids.add(sid)
        compiled = {"id": sid, "title": text(step["title"], where + ".title"),
                    "summary": text(step.get("summary", ""), where + ".summary", True), "content": []}
        has_explanation = False
        for nindex, node in enumerate(sequence(step["content"], sid + ".content", True)):
            nwhere = f"{sid}.content[{nindex}]"
            mapping(node, nwhere, {"text", "callout", "code"})
            if len(node) != 1:
                raise InputError(f"{nwhere}: each node needs exactly one of text, callout or code.")
            if "text" in node:
                value = text(node["text"], nwhere + ".text")
                compiled["content"].append({"type": "text", "html": markdown(value)})
                has_explanation = True
            elif "callout" in node:
                value = node["callout"]
                mapping(value, nwhere, {"tone", "title", "text"}, {"text"})
                tone = value.get("tone", "note")
                if tone not in ("note", "question", "tip"):
                    raise InputError(f"{nwhere}: unsupported callout tone.")
                compiled["content"].append({"type": "callout", "tone": tone,
                    "title": text(value.get("title", ""), nwhere + ".title", True),
                    "html": markdown(text(value["text"], nwhere + ".text"))})
                has_explanation = True
            else:
                value = node["code"]
                mapping(value, nwhere, {"source", "focus", "show", "context", "caption", "notes"}, {"source"})
                ref = text(value["source"], nwhere + ".source")
                if ref not in source_by_id:
                    raise InputError(f"{nwhere}: unknown source: {ref}")
                source = source_by_id[ref]
                size = len(source["lines"])
                focus = select(value.get("focus"), size, nwhere + ".focus")
                radius = value.get("context", 2)
                if type(radius) is not int or radius < 0:
                    raise InputError(f"{nwhere}.context: expected a nonnegative integer.")
                if "show" in value:
                    show = select(value["show"], size, nwhere + ".show")
                else:
                    show = set()
                    for line in focus:
                        show.update(range(max(1, line - radius), min(size, line + radius) + 1))
                    if not focus and source["kind"] in ("context", "history"):
                        show.update(range(1, size + 1))
                if not show:
                    raise InputError(f"{nwhere}: select at least one visible line using focus or show.")
                if not focus <= show:
                    raise InputError(f"{nwhere}: focused lines must be visible; hidden: {sorted(focus - show)}")
                code_id = f"{sid}-code-{nindex + 1}"
                notes = []
                for aindex, note in enumerate(sequence(value.get("notes", []), nwhere + ".notes")):
                    mapping(note, nwhere + ".note", {"lines", "text"}, {"lines", "text"})
                    anchors = select(note["lines"], size, nwhere + ".note.lines")
                    if not anchors or not anchors <= show:
                        raise InputError(f"{nwhere}: note anchors must be nonempty and initially visible.")
                    notes.append({"id": f"{code_id}-note-{aindex + 1}", "lines": sorted(anchors),
                                  "html": markdown(text(note["text"], nwhere + ".note.text"))})
                for line in focus:
                    owners.setdefault((ref, line), sid)
                compiled["content"].append({"type": "code", "id": code_id, "source": ref,
                    "label": source["label"], "language": source["language"], "kind": source["kind"],
                    "caption": text(value.get("caption", ""), nwhere + ".caption", True),
                    "focus": focus, "show": sorted(show), "notes": notes})
        if not has_explanation:
            raise InputError(f"{sid}: each step needs explanation text or a callout.")
        steps.append(compiled)
    compiled_sources = []
    for source in scope["sources"]:
        styled = highlight_lines(source)
        rows = [{"number": row["number"], "text": row["text"], "html": styled[i],
                 "operation": row["operation"], "first_step": owners.get((source["id"], row["number"]))}
                for i, row in enumerate(source["lines"])]
        compiled_sources.append({k: source[k] for k in ("id", "kind", "label", "language", "path")} | {"lines": rows})
    rendered_by_id = {s["id"]: s for s in compiled_sources}
    for step in steps:
        for node in step["content"]:
            if node["type"] == "code":
                node["lines"] = [row | {"focus": row["number"] in node["focus"]}
                                 for row in rendered_by_id[node["source"]]["lines"]]
                del node["focus"]
    model = {"title": text(raw["title"], "title"),
             "subtitle": text(raw.get("subtitle", ""), "subtitle", True),
             "intro_html": markdown(text(raw.get("intro", ""), "intro", True)),
             "language": text(raw.get("language", "zh-CN"), "language"),
             "sources": compiled_sources, "steps": steps, "draft": False}
    missing = scope["targets"] - owners.keys()
    uncovered = []
    per_source = []
    for source in scope["sources"]:
        required = [r for r in source["lines"] if r["required"]]
        remaining = [r for r in required if (source["id"], r["number"]) in missing]
        per_source.append({"id": source["id"], "required": len(required),
                           "covered": len(required) - len(remaining)})
        for row in remaining:
            number = row["number"]
            uncovered.append({"source": source["id"], "line": number,
                              "operation": row["operation"], "text": row["text"],
                              "context": [{"line": r["number"], "text": r["text"]}
                                          for r in source["lines"][max(0, number - 2):number + 1]]})
    report = {"valid": True, "complete": not missing, "scope_digest": scope["digest"],
              "required": len(scope["targets"]), "covered": len(scope["targets"]) - len(missing),
              "sources": per_source, "uncovered": uncovered}
    return model, report


def render(model):
    base = PACKAGE / "assets" / "viewer"
    try:
        template = (base / "index.html").read_text(encoding="utf-8")
        style = (base / "viewer.css").read_text(encoding="utf-8")
        script = (base / "viewer.js").read_text(encoding="utf-8")
        font = (PACKAGE / "assets" / "fonts" / "FiraCode-VF.woff2").read_bytes()
        font_license = (PACKAGE / "assets" / "fonts" / "OFL-FiraCode.txt").read_text(encoding="utf-8")
    except OSError as exc:
        raise InputError(f"Missing reader assets: {exc}") from exc
    if style.count("{{CODE_FONT}}") != 1:
        raise InputError("Reader CSS must contain exactly one {{CODE_FONT}} marker.")
    style = style.replace("{{CODE_FONT}}", base64.b64encode(font).decode("ascii"))
    for marker in ("{{STYLE}}", "{{MODEL}}", "{{SCRIPT}}"):
        if template.count(marker) != 1:
            raise InputError(f"Reader template must contain exactly one {marker} marker.")
    # Escape HTML delimiters in JSON so code such as </script> is inert data.
    data = json.dumps(model, ensure_ascii=False, separators=(",", ":"))
    data = data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    data = data.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    styles = (HtmlFormatter(style="friendly").get_style_defs(".syntax")
              + "\n/*\n" + font_license + "\n*/\n" + style)
    # Substitute once, so authored text resembling a marker cannot trigger another replacement.
    return re.sub(r"\{\{(STYLE|MODEL|SCRIPT)\}\}",
                  lambda m: {"STYLE": styles, "MODEL": data, "SCRIPT": script}[m[1]], template)


def print_report(report, as_json=False):
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    status = "PASS" if report["complete"] else "INCOMPLETE"
    print(f"{status}: {report['covered']}/{report['required']} required lines covered.")
    for line in report["uncovered"]:
        print(f"  {line['source']}:{line['line']} [{line['operation']}] {line['text']}")


def write_output(path, content):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Replace only after all validation and rendering have succeeded.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         prefix="." + target.name + ".", suffix=".tmp",
                                         dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        temporary.replace(target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version="code-board 1.0.0")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Index the scope and optionally create a walkthrough skeleton")
    prepare.add_argument("scope")
    prepare.add_argument("--out", help="Create a skeleton at this path; existing files are never overwritten")
    prepare.add_argument("--json", action="store_true")
    for name in ("check", "build"):
        sub = commands.add_parser(name)
        sub.add_argument("scope")
        sub.add_argument("walkthrough")
        sub.add_argument("--json", action="store_true", help="Print a machine-readable validation report")
        sub.add_argument("--report", help="Also save the author-side report as JSON")
        if name == "build":
            sub.add_argument("-o", "--output", required=True)
            sub.add_argument("--draft", action="store_true", help="Allow incomplete coverage, not invalid references")
    args = parser.parse_args(argv)
    try:
        scope = load_scope(args.scope)
        if args.command == "prepare":
            if args.out:
                if Path(args.out).exists():
                    raise InputError(f"Will not overwrite {args.out}. Use the new digest after reviewing references.")
                skeleton = {"version": 1, "mode": "reading", "scope_digest": scope["digest"],
                            "title": "代码讲解", "subtitle": "", "steps": []}
                write_output(args.out, yaml.safe_dump(skeleton, allow_unicode=True, sort_keys=False))
            if args.json:
                print(json.dumps({"scope_digest": scope["digest"], "required": len(scope["targets"]),
                                  "sources": scope["sources"]}, ensure_ascii=False, indent=2))
            else:
                print("scope_digest: " + scope["digest"])
                print(f"Required lines: {len(scope['targets'])}")
                for source in scope["sources"]:
                    print(f"\n[{source['id']}] {source['kind']} · {source['label']}")
                    for row in source["lines"]:
                        marker = "*" if row["required"] else " "
                        operation = {"add": "+", "delete": "-"}.get(row["operation"], " ")
                        print(f"{marker} {row['number']:4} {operation} {row['text']}")
            return 0
        model, report = compile_tutorial(scope, read_yaml(args.walkthrough))
        inputs = {Path(args.scope).resolve(), Path(args.walkthrough).resolve()}
        outputs = [Path(p).resolve() for p in (args.report, getattr(args, "output", None)) if p]
        if any(p in inputs for p in outputs) or len(outputs) != len(set(outputs)):
            raise InputError("Output/report paths must be distinct and must not overwrite either input file.")
        if args.report:
            write_output(args.report, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        if args.command == "build" and (report["complete"] or args.draft):
            resolved_output = Path(args.output).resolve()
            model["draft"] = bool(args.draft)
            write_output(args.output, render(model))
            if not args.json:
                print(f"{'Draft' if args.draft else 'Tutorial'}: {resolved_output}")
        print_report(report, args.json)
        if report["complete"] or (args.command == "build" and args.draft):
            return 0
        return 1
    except (InputError, OSError, UnicodeError) as exc:
        if getattr(args, "json", False):
            print(json.dumps({"valid": False, "complete": False, "error": str(exc)}, ensure_ascii=False))
        else:
            print("ERROR: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
