"""Token cost experiment: naive (Read+Edit tools) vs tablestakes.

Baseline: Claude Code's built-in Read and Edit tools.
- Read returns cat -n format (line numbers + content), entire content enters context
- Edit requires old_string (must be unique in file) + new_string as LLM output tokens
- Edit returns brief confirmation (small input tokens)

Design: 2×2 matrix {GFM, HTML} × {small 3r, large 18r} for reads and writes,
plus list_tables sweep with preview_rows N=0..3.

Measures both INPUT tokens (what enters LLM context) and OUTPUT tokens (what LLM
must generate for edits). Output tokens cost ~5x more per token.

Uses tiktoken cl100k_base as proxy (Claude uses a different tokenizer).

Run: uv run --with tiktoken python script.py
"""

from __future__ import annotations

import re

import tiktoken

from tablestakes.converter import html_to_rows, pipe_table_to_rows, rows_to_pipe_table
from tablestakes.hasher import compute_hash
from tablestakes.models import ColumnDescriptor
from tablestakes.parser import detect_tables

enc = tiktoken.get_encoding("cl100k_base")


def tok(text: str) -> int:
    return len(enc.encode(text))


# ---------------------------------------------------------------------------
# Row data (shared across formats to isolate format overhead)
# ---------------------------------------------------------------------------

HEADERS = ["Requirement", "Priority", "Dependency", "Priority 1-2-3"]

ROW_DATA: list[list[str]] = [
    [
        "**1.1** Agent sees only their assigned cases in the currently selected "
        "organization (case is assigned when OwnerId matches the agent's linked "
        "user ID). *(Feeds goal G1)*",
        "Must",
        "—",
        "1",
    ],
    [
        "**1.2** Case list updates in real-time without manual refresh when a "
        "new case is assigned or status changes",
        "Must",
        "Real-time event feed",
        "1",
    ],
    [
        "**1.3** Agent can filter cases by status, priority, and date range "
        "with persistent filter preferences per session",
        "Should",
        "—",
        "2",
    ],
    [
        "**2.1** View full case history including all inbound and outbound "
        "messages in chronological order",
        "Must",
        "Message API v2",
        "1",
    ],
    [
        "**2.2** Rich text editor for composing responses with formatting, "
        "inline images, and link insertion",
        "Must",
        "—",
        "1",
    ],
    [
        "**2.3** Draft auto-save every 30 seconds with recovery on session "
        "reconnect. *(Feeds goal G5)*",
        "Should",
        "—",
        "2",
    ],
    [
        "**3.1** Template library with category-based organization and "
        "full-text search across template content",
        "Must",
        "Template pipeline batch job",
        "1",
    ],
    [
        "**3.2** Variable interpolation in templates using case and customer "
        "context data (name, account, product). *(Feeds G6)*",
        "Must",
        "Customer context API",
        "1",
    ],
    [
        "**3.3** Template usage analytics showing frequency, response time "
        "impact, and customer satisfaction correlation",
        "Could",
        "Analytics pipeline",
        "3",
    ],
    [
        "**4.1** AI-generated response suggestions based on case context, "
        "customer history, and similar resolved cases",
        "Must",
        "ML inference endpoint",
        "1",
    ],
    [
        "**4.2** Confidence score displayed alongside each AI suggestion with "
        "threshold-based auto-suggest vs manual trigger",
        "Should",
        "ML inference endpoint",
        "2",
    ],
    [
        "**4.3** Agent feedback loop: accept, edit, or reject AI suggestions "
        "with reason codes for model improvement",
        "Should",
        "Feedback API",
        "2",
    ],
    [
        "**5.1** View inbound attachments in-app. PDF and image files render "
        "in-app preview; other file types offer download. *(Feeds goal G9)*",
        "Must",
        "—",
        "1",
    ],
    [
        "**5.2** Send outbound attachments as real email attachments (not URL "
        "workaround). Until the email API supports this, outbound attachments "
        "are unavailable. *(Feeds G1, G9)*",
        "Must",
        "Blocked on email API enhancement",
        "1",
    ],
    [
        "**5.3** Attachment file size and count limits are enforced with clear "
        "feedback to the user",
        "Should",
        "—",
        "",
    ],
    [
        "**6.1** SLA countdown timer visible on each case showing time "
        "remaining before breach",
        "Must",
        "SLA configuration API",
        "1",
    ],
    [
        "**6.2** Escalation workflow: automatic assignment to senior agent "
        "when SLA breach is imminent (configurable threshold)",
        "Must",
        "Routing engine v3",
        "1",
    ],
    [
        "**6.3** Post-breach handling: case flagged, manager notified, "
        "customer receives automated apology with ETA",
        "Should",
        "Notification service",
        "2",
    ],
]

SMALL_ROWS = ROW_DATA[:3]
LARGE_ROWS = ROW_DATA[:18]


# ---------------------------------------------------------------------------
# Build raw table content in both formats
# ---------------------------------------------------------------------------


def build_gitbook_html(headers: list[str], rows: list[list[str]]) -> str:
    """Collapsed single-line GitBook HTML (what's in the .md file)."""
    parts = ["<table><thead><tr>"]
    for i, h in enumerate(headers):
        if i == 0:
            parts.append(f'<th width="395.0811767578125">{h}</th>')
        else:
            parts.append(f"<th>{h}</th>")
    parts.append("</tr></thead><tbody>")
    for row in rows:
        parts.append("<tr>")
        for cell in row:
            html_cell = cell
            html_cell = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html_cell)
            html_cell = re.sub(r"\*\((.+?)\)\*", r"<em>(\1)</em>", html_cell)
            parts.append(f"<td>{html_cell}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


def build_gfm_pipe(headers: list[str], rows: list[list[str]]) -> str:
    """GFM pipe table (what's in the .md file)."""
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def build_markdown_doc(table_raw: str, section: str = "Requirements") -> str:
    """Wrap a raw table in a minimal markdown document with surrounding text."""
    return f"# Document\n\nSome intro text.\n\n## {section}\n\n{table_raw}\n\nSome text after.\n"


# Build the 4 raw tables
small_html_raw = build_gitbook_html(HEADERS, SMALL_ROWS)
large_html_raw = build_gitbook_html(HEADERS, LARGE_ROWS)
small_gfm_raw = build_gfm_pipe(HEADERS, SMALL_ROWS)
large_gfm_raw = build_gfm_pipe(HEADERS, LARGE_ROWS)


# ---------------------------------------------------------------------------
# Simulate Claude Code's Read tool output (cat -n format)
# ---------------------------------------------------------------------------


def simulate_read_tool(content: str) -> str:
    """Simulate what Claude Code's Read tool returns: cat -n formatted output."""
    lines = content.split("\n")
    parts = []
    for i, line in enumerate(lines, 1):
        # Claude Code uses: spaces + line_number + tab + content
        parts.append(f"{i:>6}\t{line}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Simulate Edit tool old_string for a cell edit
#
# The Edit tool requires old_string to be UNIQUE in the file.
# For collapsed HTML on one line, "<td>Must</td>" is likely non-unique,
# so we need preceding context to disambiguate.
# ---------------------------------------------------------------------------


def edit_old_string_html(html: str, target_row: int, target_col: int) -> str:
    """Compute the minimum unique old_string to edit a cell in collapsed HTML.

    Strategy: start with <td>value</td>, expand leftward until unique.
    """
    # Parse out the td elements in order
    td_pattern = re.compile(r"<td>(.*?)</td>", re.DOTALL)
    matches = list(td_pattern.finditer(html))
    cols = len(HEADERS)
    cell_idx = target_row * cols + target_col
    if cell_idx >= len(matches):
        return "(out of range)"

    target_match = matches[cell_idx]
    target_str = html[target_match.start() : target_match.end()]

    # If target_str is unique, that's enough
    if html.count(target_str) == 1:
        return target_str

    # Expand leftward from the target match to get unique context
    for expand in range(10, len(html), 10):
        start = max(0, target_match.start() - expand)
        candidate = html[start : target_match.end()]
        if html.count(candidate) == 1:
            return candidate

    # Worst case: everything up to and including the target
    return html[: target_match.end()]


def edit_old_string_gfm(gfm: str, target_row: int, target_col: int) -> str:
    """Compute old_string for editing a cell in a GFM pipe table.

    GFM tables have one row per line, so the whole row line is usually unique.
    """
    lines = gfm.strip().split("\n")
    # Skip header (line 0) and separator (line 1), data starts at line 2
    row_line_idx = 2 + target_row
    if row_line_idx >= len(lines):
        return "(out of range)"
    return lines[row_line_idx]


def edit_new_string_html(old_string: str, target_col: int, new_value: str) -> str:
    """Replace the target cell value in the old_string context."""
    td_matches = list(re.finditer(r"<td>(.*?)</td>", old_string, re.DOTALL))
    if not td_matches:
        return old_string
    # The target cell is the last <td>...</td> in the old_string context
    last = td_matches[-1]
    return old_string[: last.start()] + f"<td>{new_value}</td>" + old_string[last.end() :]


def edit_new_string_gfm(old_line: str, target_col: int, new_value: str) -> str:
    """Replace cell in a pipe-delimited row line."""
    cells = [c.strip() for c in old_line.strip().strip("|").split("|")]
    cells[target_col] = f" {new_value} "
    return "| " + " | ".join(c.strip() for c in cells) + " |"


# ---------------------------------------------------------------------------
# Simulate tablestakes output using REAL code
# ---------------------------------------------------------------------------


def ts_read_output(raw_table: str, section: str = "Requirements") -> str:
    """Simulate read_table output using actual tablestakes converter."""
    doc = f"## {section}\n\n{raw_table}\n"
    tables = detect_tables(doc)
    assert len(tables) == 1
    table = tables[0]
    version = compute_hash(table.raw_content)

    if table.format.value == "pipe":
        headers, rows = pipe_table_to_rows(table.raw_content)
    elif table.soup is not None:
        headers, rows = html_to_rows(table.soup)
    else:
        return "(empty)"

    columns = [ColumnDescriptor.from_header(i, h) for i, h in enumerate(headers)]
    col_display = " | ".join(c.display_name for c in columns)
    pipe = rows_to_pipe_table(headers, rows)
    fmt = table.format.value
    sec = f" [{table.section_heading}]" if table.section_heading else ""
    return f"v:{version} {fmt} {len(rows)}r {len(columns)}c{sec}\n{col_display}\n{pipe}"


def ts_list_output(
    raw_tables: list[str], sections: list[str], preview_rows: int = 1
) -> str:
    """Simulate list_tables output with configurable preview."""
    doc_parts = []
    for raw, sec in zip(raw_tables, sections):
        doc_parts.append(f"## {sec}\n\n{raw}\n\n")
    doc = "\n".join(doc_parts)
    tables = detect_tables(doc)
    parts: list[str] = [f"{len(tables)} tables\n"]

    for table in tables:
        version = compute_hash(table.raw_content)
        if table.format.value == "pipe":
            headers, rows = pipe_table_to_rows(table.raw_content)
        elif table.soup is not None:
            headers, rows = html_to_rows(table.soup)
        else:
            continue
        columns = [ColumnDescriptor.from_header(i, h) for i, h in enumerate(headers)]
        col_display = " | ".join(c.display_name for c in columns)
        fmt = table.format.value
        sec_label = f" [{table.section_heading}]" if table.section_heading else ""
        parts.append(
            f"T{table.index} {fmt} {len(rows)}r {len(headers)}c v:{version}{sec_label}"
        )
        parts.append(f"  {col_display}")
        for row_idx, row in enumerate(rows[:preview_rows]):
            cells = " | ".join(row[: len(headers)])
            parts.append(f"  row{row_idx}: {cells}")
        parts.append("")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Run the experiment
# ---------------------------------------------------------------------------

print("=" * 72)
print("  TOKEN COST EXPERIMENT: Claude Code (Read+Edit) vs tablestakes")
print("  Tokenizer: tiktoken cl100k_base (GPT-4 proxy)")
print("=" * 72)


# ===== EXPERIMENT 1: READ (input tokens — what enters LLM context) =====

print("\n" + "=" * 72)
print("  EXPERIMENT 1: READ — input tokens entering LLM context")
print("=" * 72)
print()
print("  Baseline: Claude Code Read tool (cat -n format, full file)")
print("  Treatment: tablestakes read_table (metadata + pipe table)")
print()

read_results: dict[str, tuple[int, int, float]] = {}

for label, raw, rows_used in [
    ("Small HTML (3r × 4c)", small_html_raw, SMALL_ROWS),
    ("Large HTML (18r × 4c)", large_html_raw, LARGE_ROWS),
    ("Small GFM  (3r × 4c)", small_gfm_raw, SMALL_ROWS),
    ("Large GFM  (18r × 4c)", large_gfm_raw, LARGE_ROWS),
]:
    doc = build_markdown_doc(raw)
    naive = simulate_read_tool(doc)
    ts = ts_read_output(raw)

    n = tok(naive)
    t = tok(ts)
    s = (1 - t / n) * 100

    sign = "+" if s < 0 else ""
    print(f"  {label}")
    print(f"    Read tool:   {n:>5} tok  (full file, cat -n format)")
    print(f"    read_table:  {t:>5} tok  (table only, pipe format)")
    print(f"    Savings:     {sign}{s:.1f}%")
    print()

    key = label.split("(")[0].strip().lower().replace(" ", "_")
    read_results[key] = (n, t, s)


# ===== EXPERIMENT 2: WRITE — output tokens (LLM generates old/new_string) =====

print("=" * 72)
print("  EXPERIMENT 2: WRITE — LLM output tokens per cell edit")
print("=" * 72)
print()
print("  Baseline: Edit tool (old_string must be unique + new_string)")
print("  Treatment: update_cells (row/column/value JSON + v:hash response)")
print()
print("  Scenario: change row 0, column 1 (Priority) from 'Must' to 'Should'")
print()

TS_WRITE_RESPONSE = "v:5749c94ffb1f"

write_results: dict[str, dict[str, int]] = {}

for label, raw, is_html in [
    ("Large HTML (18r × 4c)", large_html_raw, True),
    ("Large GFM  (18r × 4c)", large_gfm_raw, False),
]:
    print(f"  {label}")

    if is_html:
        old = edit_old_string_html(raw, target_row=0, target_col=1)
        new = edit_new_string_html(old, target_col=1, new_value="Should")
    else:
        old = edit_old_string_gfm(raw, target_row=0, target_col=1)
        new = edit_new_string_gfm(old, 1, "Should")

    # Edit tool: LLM output = old_string + new_string
    edit_output = tok(old) + tok(new)
    # Edit tool: response back to LLM (brief confirmation)
    edit_response = tok("Edit applied to file.md")

    # tablestakes: LLM output = update_cells JSON args
    ts_call = '{"row": 0, "column": "B", "value": "Should"}'
    ts_output = tok(ts_call)
    ts_response = tok(TS_WRITE_RESPONSE)

    print(f"    --- Edit tool ---")
    print(f"    old_string:  {tok(old):>4} tok  ({len(old):>4} chars)")
    print(f"    new_string:  {tok(new):>4} tok  ({len(new):>4} chars)")
    print(f"    LLM output:  {edit_output:>4} tok  (old + new, ~5x cost multiplier)")
    print(f"    Response:    {edit_response:>4} tok  (confirmation)")
    print(f"    old_string preview: {old[:80]!r}...")
    print()
    print(f"    --- tablestakes ---")
    print(f"    LLM output:  {ts_output:>4} tok  ({ts_call!r})")
    print(f"    Response:    {ts_response:>4} tok  ({TS_WRITE_RESPONSE!r})")
    print()

    total_edit = edit_output + edit_response
    total_ts = ts_output + ts_response
    s = (1 - total_ts / total_edit) * 100
    print(f"    Total (out+in): Edit={total_edit} tok  vs  tablestakes={total_ts} tok  ({s:.0f}% savings)")
    print()

    key = "html" if is_html else "gfm"
    write_results[key] = {
        "edit_output": edit_output,
        "edit_response": edit_response,
        "ts_output": ts_output,
        "ts_response": ts_response,
    }


# ===== EXPERIMENT 3: 10-EDIT WORKFLOW =====

print("=" * 72)
print("  EXPERIMENT 3: 10-EDIT WORKFLOW (1 read + 10 cell edits)")
print("=" * 72)
print()
print("  Baseline: Read file once + 10 × Edit(old_string, new_string)")
print("  Treatment: read_table once + 10 × update_cells + v:hash response")
print()

for label, raw, is_html in [
    ("HTML (18r × 4c)", large_html_raw, True),
    ("GFM  (18r × 4c)", large_gfm_raw, False),
]:
    doc = build_markdown_doc(raw)
    key = "html" if is_html else "gfm"
    w = write_results[key]

    # Naive: Read tool input + 10 × (Edit output + Edit response)
    read_input = tok(simulate_read_tool(doc))
    naive_total = read_input + 10 * (w["edit_output"] + w["edit_response"])

    # tablestakes: read_table input + 10 × (update_cells output + v:hash response)
    ts_read_input = tok(ts_read_output(raw))
    ts_total = ts_read_input + 10 * (w["ts_output"] + w["ts_response"])

    s = (1 - ts_total / naive_total) * 100

    print(f"  {label}:")
    print(f"    Naive:       {naive_total:>6} tok  ({read_input} read + 10 × {w['edit_output'] + w['edit_response']} edit)")
    print(f"    tablestakes: {ts_total:>6} tok  ({ts_read_input} read + 10 × {w['ts_output'] + w['ts_response']} edit)")
    print(f"    Savings:     {s:.1f}%")
    print()


# ===== EXPERIMENT 4: LIST_TABLES — preview_rows sweep =====

print("=" * 72)
print("  EXPERIMENT 4: LIST_TABLES — discovery cost, preview_rows N=0..3")
print("=" * 72)
print()
print("  Baseline: Read full file (LLM scans all content to find tables)")
print("  Treatment: list_tables (compact metadata + N preview rows)")
print()

raw_tables_26 = [build_gitbook_html(HEADERS, LARGE_ROWS)] * 26
sections_26 = [f"Section {i}" for i in range(26)]

naive_doc_parts = []
for raw_t, sec in zip(raw_tables_26, sections_26):
    naive_doc_parts.append(f"## {sec}\n\n{raw_t}\n\n")
naive_full_doc = "\n".join(naive_doc_parts)
naive_read = simulate_read_tool(naive_full_doc)
naive_tok_val = tok(naive_read)

print(f"  Naive (Read full file): {naive_tok_val:>6} tok\n")

for n_preview in [0, 1, 2, 3]:
    ts_list = ts_list_output(raw_tables_26, sections_26, preview_rows=n_preview)
    t = tok(ts_list)
    s = (1 - t / naive_tok_val) * 100
    print(f"  preview_rows={n_preview}: {t:>5} tok  savings: {s:.1f}%")

print()


# ===== SUMMARY TABLE =====

print("=" * 72)
print("  SUMMARY TABLE (18-row HTML table, preview_rows=1)")
print("=" * 72)
print()
print("| Operation | Read+Edit | tablestakes | Savings |")
print("|---|---|---|---|")

# list_tables
ts_list_n1 = ts_list_output(raw_tables_26, sections_26, preview_rows=1)
s = (1 - tok(ts_list_n1) / naive_tok_val) * 100
print(f"| `list_tables` (26 tables) | ~{naive_tok_val:,} tok | ~{tok(ts_list_n1):,} tok | **{s:.0f}%** |")

# read_table HTML
n, t, s = read_results["large_html"]
print(f"| `read_table` (18r HTML) | ~{n:,} tok | ~{t:,} tok | **{s:.0f}%** |")

# read_table GFM
n, t, s = read_results["large_gfm"]
sign = "+" if s < 0 else ""
print(f"| `read_table` (18r GFM) | ~{n:,} tok | ~{t:,} tok | {sign}{s:.0f}% (pass-through) |")

# write HTML
w = write_results["html"]
e = w["edit_output"] + w["edit_response"]
t = w["ts_output"] + w["ts_response"]
s = (1 - t / e) * 100
print(f"| Cell edit (18r HTML) | ~{e} tok | ~{t} tok | **{s:.0f}%** |")

# 10-edit workflow
doc = build_markdown_doc(large_html_raw)
read_n = tok(simulate_read_tool(doc))
w = write_results["html"]
naive_wf = read_n + 10 * (w["edit_output"] + w["edit_response"])
ts_wf = tok(ts_read_output(large_html_raw)) + 10 * (w["ts_output"] + w["ts_response"])
s = (1 - ts_wf / naive_wf) * 100
print(f"| 10-edit workflow (HTML) | ~{naive_wf:,} tok | ~{ts_wf:,} tok | **{s:.0f}%** |")

print()
print("Methodology: tiktoken cl100k_base. Baseline = Claude Code Read+Edit tools.")
print("Read = input tokens (file content). Write = output tokens (old_string + new_string).")
print("Output tokens cost ~5x more than input tokens.")
