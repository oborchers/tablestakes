"""Experiment: Is sort_table / filter worth adding?

The question: when the LLM needs to reorder or filter a table IN-PLACE,
it must currently use replace_table and generate the entire table as output tokens.
A dedicated tool would take just a column name + direction.

Run: uv run --with tiktoken python experiment_sort.py
"""

from __future__ import annotations

import tiktoken

from tablestakes.converter import rows_to_pipe_table

enc = tiktoken.get_encoding("cl100k_base")


def tok(text: str) -> int:
    return len(enc.encode(text))


HEADERS = ["Requirement", "Priority", "Dependency", "Priority 1-2-3"]

ROWS_18 = [
    ["**1.1** Agent sees only their assigned cases", "Must", "—", "1"],
    ["**1.2** Case list updates in real-time", "Must", "Real-time event feed", "1"],
    ["**1.3** Agent can filter cases by status", "Should", "—", "2"],
    ["**2.1** View full case history", "Must", "Message API v2", "1"],
    ["**2.2** Rich text editor for composing responses", "Must", "—", "1"],
    ["**2.3** Draft auto-save every 30 seconds", "Should", "—", "2"],
    ["**3.1** Template library with category-based org", "Must", "Template pipeline", "1"],
    ["**3.2** Variable interpolation in templates", "Must", "Customer context API", "1"],
    ["**3.3** Template usage analytics", "Could", "Analytics pipeline", "3"],
    ["**4.1** AI-generated response suggestions", "Must", "ML inference endpoint", "1"],
    ["**4.2** Confidence score alongside AI suggestions", "Should", "ML inference endpoint", "2"],
    ["**4.3** Agent feedback loop for AI suggestions", "Should", "Feedback API", "2"],
    ["**5.1** View inbound attachments in-app", "Must", "—", "1"],
    ["**5.2** Send outbound attachments as email", "Must", "Email API enhancement", "1"],
    ["**5.3** Attachment file size limits enforced", "Should", "—", ""],
    ["**6.1** SLA countdown timer on each case", "Must", "SLA configuration API", "1"],
    ["**6.2** Escalation workflow for SLA breach", "Must", "Routing engine v3", "1"],
    ["**6.3** Post-breach handling and notification", "Should", "Notification service", "2"],
]

full_pipe = rows_to_pipe_table(HEADERS, ROWS_18)

print("=" * 72)
print("  EXPERIMENT: sort_table / filter value analysis")
print("  Tokenizer: tiktoken cl100k_base")
print("=" * 72)

# --- SORT ---
print("\n## SORT TABLE IN-PLACE (18 rows × 4 cols)")
print()

# Naive: replace_table — LLM generates full reordered pipe table
replace_call = f'{{"new_content": "{full_pipe}"}}'  # simplified
replace_output = tok(full_pipe)

# sort_table tool
sort_call = '{"column": "B", "order": "asc"}'
sort_output = tok(sort_call)

print(f"  replace_table (full pipe):  {replace_output:>4} output tok  (LLM regenerates entire table)")
print(f"  sort_table tool:            {sort_output:>4} output tok  (column + direction)")
print(f"  Savings: {(1 - sort_output / replace_output) * 100:.0f}%")
print(f"  At 5x output cost: {replace_output * 5} vs {sort_output * 5} effective tokens")
print()

# --- FILTER (delete rows not matching) ---
print("## FILTER TABLE IN-PLACE (keep only 'Must' rows, 11 of 18)")
print()

# Count Must rows
must_rows = [r for r in ROWS_18 if r[1] == "Must"]
non_must_rows = [r for r in ROWS_18 if r[1] != "Must"]

# Naive option A: replace_table with filtered content
filtered_pipe = rows_to_pipe_table(HEADERS, must_rows)
replace_filtered = tok(filtered_pipe)

# Naive option B: delete_row for each non-Must row (7 calls, each needs version chaining)
delete_calls = []
for i, row in enumerate(ROWS_18):
    if row[1] != "Must":
        delete_calls.append(f'{{"row_index": {i}}}')
delete_output = sum(tok(c) for c in delete_calls)

# filter_table tool
filter_call = '{"column": "B", "match": "Must"}'
filter_output = tok(filter_call)

print(f"  Option A: replace_table (filtered pipe): {replace_filtered:>4} output tok")
print(f"  Option B: {len(non_must_rows)}× delete_row:              {delete_output:>4} output tok + {len(non_must_rows)} round trips + version chaining")
print(f"  filter_table tool:                       {filter_output:>4} output tok")
print()
print(f"  Savings vs replace: {(1 - filter_output / replace_filtered) * 100:.0f}%")
print(f"  Savings vs delete:  {(1 - filter_output / delete_output) * 100:.0f}% (plus eliminates {len(non_must_rows)} round trips)")
print()

# --- MOVE ROW ---
print("## MOVE ROW (reorder row 15 to position 2)")
print()

# Naive: replace_table with reordered content (full table output)
print(f"  replace_table:  {replace_output:>4} output tok  (LLM regenerates entire table)")

move_call = '{"from_row": 15, "to_row": 2}'
move_output = tok(move_call)
print(f"  move_row tool:  {move_output:>4} output tok")
print(f"  Savings: {(1 - move_output / replace_output) * 100:.0f}%")
print()

# --- SUMMARY ---
print()
print("=" * 72)
print("  SUMMARY: output tokens per operation (18-row table)")
print("=" * 72)
print()
print("| Operation | Current approach | Dedicated tool | Savings |")
print("|---|---|---|---|")
print(f"| Sort | ~{replace_output} tok (replace_table) | ~{sort_output} tok (sort_table) | **{(1 - sort_output / replace_output) * 100:.0f}%** |")
print(f"| Filter (keep 11/18) | ~{replace_filtered} tok (replace_table) | ~{filter_output} tok (filter_table) | **{(1 - filter_output / replace_filtered) * 100:.0f}%** |")
print(f"| Move row | ~{replace_output} tok (replace_table) | ~{move_output} tok (move_row) | **{(1 - move_output / replace_output) * 100:.0f}%** |")
print()
print("Key question: how OFTEN do LLMs sort/filter/move in real workflows?")
print("If rare → not worth the tool surface area.")
print("If common → significant savings on output tokens (5x cost multiplier).")
