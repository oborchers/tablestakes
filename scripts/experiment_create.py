"""Experiment: Is create_table worth adding?

Measures LLM OUTPUT tokens (the expensive ones, ~5x cost) for creating a new table.

Scenario: LLM needs to create a 5-row, 4-column requirements table in a markdown
file that uses GitBook collapsed HTML format.

Baseline A: LLM writes raw HTML via Edit/Write tool (must generate all tags)
Baseline B: LLM writes GFM pipe table via Edit/Write tool (just pipe syntax)
Treatment:  LLM calls create_table with pipe content (tablestakes converts to HTML)

Run: uv run --with tiktoken python experiment_create.py
"""

from __future__ import annotations

import re

import tiktoken

from tablestakes.converter import rows_to_pipe_table

enc = tiktoken.get_encoding("cl100k_base")


def tok(text: str) -> int:
    return len(enc.encode(text))


# ---------------------------------------------------------------------------
# The table content (same data, different formats the LLM must generate)
# ---------------------------------------------------------------------------

HEADERS = ["Requirement", "Priority", "Dependency", "Priority 1-2-3"]

ROWS = [
    ["**5.1** View inbound attachments in-app. PDF and image files render "
     "in-app preview; other file types offer download. *(Feeds goal G9)*",
     "Must", "—", "1"],
    ["**5.2** Send outbound attachments as real email attachments (not URL "
     "workaround). Until the email API supports this, outbound attachments "
     "are unavailable. *(Feeds G1, G9)*",
     "Must", "Blocked on email API enhancement", "1"],
    ["**5.3** Attachment file size and count limits are enforced with clear "
     "feedback to the user",
     "Should", "—", ""],
    ["**5.4** Drag-and-drop attachment upload from desktop with progress "
     "indicator and cancel support",
     "Could", "—", "3"],
    ["**5.5** Attachment virus scanning before delivery to recipient with "
     "quarantine workflow for flagged files",
     "Should", "Security scanning API", "2"],
]

# --- Baseline A: LLM generates collapsed GitBook HTML ---

def build_html_output() -> str:
    """What the LLM would write via Write/Edit tool for an HTML table."""
    parts = ['<table><thead><tr>']
    for i, h in enumerate(HEADERS):
        if i == 0:
            parts.append(f'<th width="395.0811767578125">{h}</th>')
        else:
            parts.append(f"<th>{h}</th>")
    parts.append("</tr></thead><tbody>")
    for row in ROWS:
        parts.append("<tr>")
        for cell in row:
            html_cell = cell
            html_cell = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html_cell)
            html_cell = re.sub(r"\*\((.+?)\)\*", r"<em>(\1)</em>", html_cell)
            parts.append(f"<td>{html_cell}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


# --- Baseline B: LLM generates GFM pipe table ---

def build_gfm_output() -> str:
    """What the LLM would write via Write/Edit tool for a GFM table."""
    lines = []
    lines.append("| " + " | ".join(HEADERS) + " |")
    lines.append("| " + " | ".join("---" for _ in HEADERS) + " |")
    for row in ROWS:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


# --- Treatment: LLM calls create_table with pipe content ---

def build_create_table_call() -> str:
    """What the LLM would pass as the content arg to a hypothetical create_table tool.

    Just pipe table content — tablestakes handles HTML conversion.
    """
    return rows_to_pipe_table(HEADERS, ROWS)


# --- Also measure: batch format operation ---
# Scenario: Bold all values in column A (Requirement) that don't already have bold

def batch_format_naive() -> str:
    """Naive: 5 individual update_cells calls to add bold to column A."""
    calls = []
    for i, row in enumerate(ROWS):
        # Each call is a JSON payload
        calls.append(f'{{"row": {i}, "column": "A", "value": "**{row[0]}**"}}')
    return "\n".join(calls)


def batch_format_tool() -> str:
    """Hypothetical format_cells tool: single call."""
    return '{"column": "A", "format": "bold"}'


# ---------------------------------------------------------------------------
# Run experiment
# ---------------------------------------------------------------------------

print("=" * 72)
print("  EXPERIMENT: create_table and batch format value analysis")
print("  Tokenizer: tiktoken cl100k_base")
print("=" * 72)

html_out = build_html_output()
gfm_out = build_gfm_output()
pipe_out = build_create_table_call()

print("\n## CREATE TABLE (5 rows × 4 cols)")
print()
print("LLM must generate this content as OUTPUT tokens (~5x cost):")
print()

print(f"  A) Write collapsed HTML:   {tok(html_out):>4} tok  ({len(html_out):>4} chars)")
print(f"  B) Write GFM pipe table:   {tok(gfm_out):>4} tok  ({len(gfm_out):>4} chars)")
print(f"  C) create_table(pipe):     {tok(pipe_out):>4} tok  ({len(pipe_out):>4} chars)")
print()

s_html = (1 - tok(pipe_out) / tok(html_out)) * 100
s_gfm = (1 - tok(pipe_out) / tok(gfm_out)) * 100
print(f"  Savings vs HTML: {s_html:.1f}%")
print(f"  Savings vs GFM:  {s_gfm:.1f}%  (pipe is same content, no savings)")
print()

print("  --- HTML output the LLM must generate (first 200 chars) ---")
print(f"  {html_out[:200]}")
print()
print("  --- create_table pipe content (first 200 chars) ---")
print(f"  {pipe_out[:200]}")
print()

# Key insight: create_table's value is NOT in the pipe content (same tokens as GFM).
# It's that the LLM doesn't need to generate HTML tags.
html_tokens = tok(html_out)
pipe_tokens = tok(pipe_out)
tag_overhead = html_tokens - pipe_tokens
print(f"  HTML tag overhead: {tag_overhead} tokens ({tag_overhead/html_tokens*100:.0f}% of HTML output)")
print(f"  At ~5x output cost: {tag_overhead} wasted output tokens = ~{tag_overhead * 5} effective tokens")


print()
print()
print("## BATCH FORMAT (bold column A, 5 rows)")
print()

naive_fmt = batch_format_naive()
tool_fmt = batch_format_tool()

print(f"  Naive (5× update_cells):   {tok(naive_fmt):>4} tok  (LLM generates 5 JSON payloads)")
print(f"  format_cells tool:         {tok(tool_fmt):>4} tok  (single call)")
print(f"  Savings: {(1 - tok(tool_fmt) / tok(naive_fmt)) * 100:.0f}%")
print()
print("  But note: the naive approach also requires 5 separate tool calls")
print("  (5× round-trip overhead, 5× version hash management)")
print()

# Scale to 18 rows
naive_18 = []
for i in range(18):
    row_content = f"**{i+1}.1** Some requirement text for row {i}"
    naive_18.append(f'{{"row": {i}, "column": "A", "value": "**{row_content}**"}}')
naive_18_str = "\n".join(naive_18)

print(f"  Scaled to 18 rows:")
print(f"    Naive (18× update_cells): {tok(naive_18_str):>4} tok")
print(f"    format_cells tool:        {tok(tool_fmt):>4} tok")
print(f"    Savings: {(1 - tok(tool_fmt) / tok(naive_18_str)) * 100:.0f}%")

print()
print()
print("## VERDICT")
print()
print("  create_table:")
print(f"    HTML tag overhead = {tag_overhead} output tokens per 5-row table")
print(f"    Scales linearly with rows. For 18 rows: ~{int(tag_overhead * 18/5)} wasted output tokens")
print("    ALSO: LLMs frequently corrupt HTML structure (missed closing tags,")
print("    wrong nesting). create_table eliminates that error class entirely.")
print("    VERDICT: Worth adding for HTML tables. Zero value for GFM.")
print()
print("  format_cells / batch format:")
print("    Saves output tokens but more importantly saves ROUND TRIPS.")
print("    5 update_cells = 5 tool calls = 5× latency + version chaining.")
print("    A batch format tool = 1 call.")
print("    VERDICT: Nice-to-have. Can be done with update_cells today.")
print()
print("  slice / range read:")
print(f"    read_table (18r) = 688 tok. A 3-row slice ≈ ~150 tok.")
print(f"    Savings: ~540 tok. But LLMs usually need full context.")
print("    VERDICT: Low value. Only matters for 50+ row tables.")
print()
print("  search / sort / filter:")
print("    LLM has full table in context. Can reason about it directly.")
print("    VERDICT: No value. Adding tools costs more than it saves.")
