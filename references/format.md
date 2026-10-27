# code-board author format · version 1

Two UTF-8 YAML files are authored: `scope.yaml` and `walkthrough.yaml`. JSON is also accepted because it is a YAML subset. Duplicate keys, aliases, unknown fields and malformed ranges are rejected. Use spaces for YAML indentation. YAML literal blocks (`|`) preserve code indentation and line breaks.

## Scope

```yaml
version: 1
sources:
  - id: read-user
    kind: diff
    language: javascript
    label: 用户读取 · user.js
    path: src/user.js
    content: |2
       function readUser(id) {
      -  return users[id];
      +  const user = users[id];
      +  if (!user) throw new Error("User not found");
      +  return user;
       }
```

The diff above has **six source rows**. The leading operation character occupies a real column inside the literal block. The code's indentation follows it. Source references refer to these rows, not the displayed original-file coordinates.

Top-level fields: `version` (required, integer 1), `sources` (required, nonempty list).

Source fields:

| Field | Meaning |
| --- | --- |
| `id` | Required unique ID; start with an ASCII letter, then letters, digits, `_`, `-`. |
| `kind` | Required: `code`, `diff`, `context`, or `history`. |
| `content` | Required literal source text. |
| `language` | Syntax-highlighting language; defaults to `text`. Unknown names render as plain text. |
| `label` | Reader-facing source caption; defaults to `path`, then ID. |
| `path` | Optional display metadata. Never read from disk by the tool. |

Kinds and coverage:

- `code`: every physical row is required, including empty and structural rows.
- `diff`: each line begins with exactly one operation prefix: `+` added, `-` deleted, or a space for context. Added and deleted lines are required. Modifications therefore require both sides. Do not include `diff --git`, `---`/`+++` file headers or `@@` hunk headers. Split disconnected hunks into separate source entries when useful. A blank added row is `+`; a blank context row is a single space.
- `context`: supporting source text, never counted toward coverage.
- `history`: an actual preserved intermediate implementation, allowed only in `authored` mode. Never counted toward final scope coverage.

A terminating newline ends the final row; it does not create another row. Additional blank lines do count. The entire scope must contain at least one required row. There is no `ignore`, exclusion, manual coverage field, repository resolver or patch application.

### Preserve original indentation

YAML normally infers block indentation from the first nonempty row and removes that common indentation. Use an explicit `|2` indicator when a diff starts with a space-prefixed context row, or when copied code already has outer indentation. This makes the YAML indentation exactly two spaces deeper than the `content` key; any additional spaces are source characters. The diff example above uses this form intentionally. For snippets originally nested inside another function, preserve their outer spaces beyond those two YAML indentation spaces. Inspect the prepared index and compare with the original source before writing the explanation.

When splitting a complete file into source chunks, keep each physical line exactly once. Use `|2+` for chunks ending in blank lines so YAML preserves those rows; the Snake example uses this form. Splitting into readable units must not silently remove blank lines from the selected scope.

## Prepare

```bash
python "<skill>/scripts/code-board.py" prepare scope.yaml --out walkthrough.yaml
python "<skill>/scripts/code-board.py" prepare scope.yaml --json
```

`prepare` outputs source IDs, row numbers, required markers, code and `scope_digest`. `--out` creates a skeleton without overwriting an existing file. It defaults to reading mode and zero steps, which is intentionally incomplete. `--json` provides a machine-readable index. The digest binds all source identities, contents and metadata to the walkthrough. Source edits require reindexing and reviewing the old references before updating the digest. Do not let the agent silently shorten the selected scope to pass validation.

## Walkthrough

```yaml
version: 1
mode: reading
scope_digest: COPY_THE_DIGEST_FROM_PREPARE
title: 找不到用户时，应该发生什么
subtitle: 从正常读取，到明确的失败路径。
intro: |
  先理解读取成功时的行为，再看缺失数据如何改变返回路径。
language: zh-CN
steps:
  - id: missing-user
    title: 将缺失数据变成明确的错误
    summary: 调用方需要知道这次读取没有成功。
    content:
      - text: |
          旧实现直接返回查询结果。这里先保存结果，再检查用户是否存在。
          **这改变了失败时的行为**：调用方会收到错误。
      - code:
          source: read-user
          focus: ["2-5"]
          show: ["1-6"]
          caption: 旧的直接返回被替换为检查后返回。
          notes:
            - lines: "4"
              text: 这里的错误会交给调用方处理。
      - callout:
          tone: question
          title: 调用方需要作出什么调整？
          text: 它需要处理这条错误路径，才能向用户提供清晰反馈。
```

Required top-level fields: `version`, `mode`, `scope_digest`, `title`, `steps`.
Optional fields: `subtitle`, `intro`, `language`.

`mode` is `reading` or `authored`. Reading mode rejects scopes containing history sources. Authored mode permits real historical material, but the tool cannot verify its historical truth; the author must know and preserve the actual versions.

Each step has a unique `id`, nonempty `title`, optional `summary`, and a nonempty `content` list. A step needs at least one nonempty text or callout node. Content order is preserved, allowing prose/code/prose/code. There is no fixed number of steps or line-per-step limit.

### Text and callouts

`text` is a Markdown string. Supported subset: paragraphs, inline `code`, **bold**, *emphasis*, safe links, simple unordered/ordered lists, blockquotes, and `###` headings. Separate blocks with a blank line; keep list items on individual lines. Raw HTML is escaped. Fenced code is rejected in text: put code in a declared source and reference it. Nested Markdown, tables, embedded images and executable HTML are not part of version 1.

`callout` has `text` (required), optional `title`, and optional `tone`: `note`, `question`, or `tip`. It is reader-facing explanatory content, not a validation result.

### Code views

| Field | Meaning |
| --- | --- |
| `source` | Required source ID. |
| `focus` | Rows actively explained in this view; these receive emphasis and may earn coverage. |
| `show` | Optional rows initially displayed. Must contain every focus row. Gaps become expandable omissions. |
| `context` | Neighboring row radius when `show` is omitted; default 2. |
| `caption` | Optional short caption below the code view. |
| `notes` | Optional temporary code comments. Each has `lines` and Markdown `text`. Write only the explanation; the viewer supplies comment delimiters. |

A row selector accepts an integer, a string such as `"3"`, an inclusive range `"3-7"`, `"all"`, or a list combining them. For example, `focus: ["1-2", "5", "8-11"]`. Ranges must be within that source's row count. Duplicate selections are merged. Focus can include context rows for emphasis, but context still does not earn coverage.

If `show` is omitted, the viewer initially shows focus rows and their configured neighbors. A history/context source with no focus defaults to showing the whole snippet. A code/diff source needs `focus` or `show`; merely showing a required row does not count as explaining it. Notes require at least one anchor row, and all their anchors must be initially visible.

Notes appear directly inside the snippet, at their first anchor, with the same indentation as that code. A single short note sits at the end of the line when it fits; otherwise it appears above the line and wraps within the code viewport. Notes spanning several rows, or multiple notes on one row, stay above the first anchor in authored order. There are no numbered markers or separate footnotes. Keep notes concise and use the surrounding prose for longer reasoning. Comment delimiters follow the source language (`<!-- -->` for HTML/XML, `/* */` for CSS, `#` or `--` for common scripting languages, `//` otherwise). These are display-only comments, so they do not consume source line numbers, change coverage, enter the source inspector, or enter copied code. Leave the original source untouched.

Readers can expand omitted context. This does not change coverage. Code is read from the source text, never supplied again by a view. The reader's copy control excludes removed lines, diff prefixes, row numbers, annotations and omission labels. A fragment with omitted lines remains a fragment when copied.

### Coverage

Coverage is the union of required rows selected in valid focus views, attached to steps containing explanatory text and actually included in the initial display. Duplicate views do not inflate it. The first explanatory step is recorded for source-to-step navigation. Blank rows and braces can be explained as part of their surrounding block; no individual prose per row is required.

The renderer and validator consume the same compiled code-view representation. A hidden focus row, unknown source, dangling note or empty explanation is an error. References cannot claim coverage for text that the reader cannot see. Prose correctness and the completeness of the author's selected scope relative to an external request remain author responsibilities.

## Check and export

```bash
python "<skill>/scripts/code-board.py" check scope.yaml walkthrough.yaml --json --report report.json
python "<skill>/scripts/code-board.py" build scope.yaml walkthrough.yaml -o tutorial.html
python "<skill>/scripts/code-board.py" build scope.yaml walkthrough.yaml --draft -o preview.html
```

Exit codes: `0` successful check/build, `1` incomplete coverage, `2` invalid input or an execution error. Explicit draft build returns `0` for valid-but-incomplete input and labels the page as a draft; it still rejects invalid references. Never use a draft build as the completion check.

The JSON report contains `valid`, `complete`, `required`, `covered`, per-source counts, and `uncovered` entries with neighboring context. Reports stay author-side. An unsuccessful formal build does not overwrite an existing output. An earlier output, if present, remains an older artifact; the failed command does not certify it.

The exported HTML embeds viewer CSS, JavaScript, syntax coloring, source data and tutorial content. It uses system fonts and requires no network requests. The fixed dark desktop layout uses neutral charcoal backgrounds with Monokai Classic syntax colors and contains a chapter outline, a compact document heading, and the explanation itself. Source strings and annotation markup are escaped; they are not executed.
