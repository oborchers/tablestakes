# Test Document

## Cross-Domain Dependencies

| Integration                                                         | Source                       | Requirements       |
| ------------------------------------------------------------------- | ---------------------------- | ------------------ |
| **Template response source** (matched template, pre-filled content) | Batch pipeline → Database    | 6.5, 6.6, 6.7, 7.7 |
| **AI response source** (proactive draft)                            | Batch pipeline → Database    | 4.2, 7.2           |
| **On-demand AI generation** (interactive mode)                      | Streaming pipeline (FastAPI) | 1.6                |

Some text between tables.

### Attachments

<table><thead><tr><th width="395.0811767578125">Requirement</th><th>Priority</th><th>Dependency</th><th>Priority 1-2-3</th></tr></thead><tbody><tr><td><strong>5.1</strong> View inbound attachments in-app. PDF and image files render in-app preview; other file types offer download. <em>(Feeds goal G9)</em></td><td>Must</td><td>—</td><td>1</td></tr><tr><td><strong>5.2</strong> Send outbound attachments as real email attachments (not URL workaround).</td><td>Must</td><td>Blocked on email API enhancement</td><td>1</td></tr><tr><td><strong>5.3</strong> Attachment file size and count limits are enforced with clear feedback to the user</td><td>Should</td><td>—</td><td></td></tr></tbody></table>

### Notifications

| Requirement | Priority |
| --- | --- |
| **12.1** In-app notification center | Must |
| **12.2** Notification triggers | Must |
| **12.3** Each notification links to the relevant case | Must |

## Code Block (should NOT be detected as table)

```html
<table><tr><td>This is inside a code block</td></tr></table>
```

```markdown
| Not | A | Table |
| --- | --- | --- |
| Inside | Code | Block |
```

## Simple HTML table (no GitBook attrs)

<table>
<thead><tr><th>Name</th><th>Age</th></tr></thead>
<tbody><tr><td>Alice</td><td>30</td></tr><tr><td>Bob</td><td>25</td></tr></tbody>
</table>

End of document.
