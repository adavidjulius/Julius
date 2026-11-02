---
name: file-reading
description: "Use this skill when a file has been uploaded or referenced in Julius, but its full content is NOT in your context — only its file path (e.g. /mnt/user-data/uploads/ or local workspace path) is provided. This skill is a router: it tells you which tool to use for each file type (pdf, docx, xlsx, csv, json, images, archives, ebooks) so you read the right amount the right way instead of blindly dumping a binary or flooding context. Triggers: any mention of /mnt/user-data/uploads/, uploaded files, file_path tags, or user asking about an uploaded/workspace file not yet in context. Do NOT use this skill if the file content is already visible in your context."
compatibility: "Julius Workspace, Antigravity IDE"
license: Proprietary
---

# Reading Files in Julius

## Why this skill exists

When a user uploads a file or references a file in Julius, the file is available at a path on disk (e.g. `/mnt/user-data/uploads/<filename>` or inside the workspace). **The complete raw content may not be in your LLM context window.** You must read or sample it appropriately.

The naive action — running `cat` or dumping large binary/data files directly — is ineffective:

- On a PDF or binary file, it outputs unreadable garbage.
- On a massive CSV or log file, it floods the context window with unnecessary rows.
- On a DOCX/XLSX/PPTX, it prints compressed ZIP bytes.
- On images or media, raw text tools cannot extract semantic data.

This skill provides the optimal first move for each file type in Julius, leveraging built-in tools (`view_file`, `grep_search`) and shell tools (`run_command`).

---

## General Protocol for Julius

1. **Check file extension & size first.**
   ```bash
   stat -c '%s bytes, %y' /path/to/file.pdf
   file /path/to/file.pdf
   ```
2. **Use built-in Julius tools when appropriate.**
   - For source code, text files, and moderate logs: Use `view_file`.
   - For specific text patterns: Use `grep_search`.
   - For PDFs, images, audio, video: `view_file` supports media & PDF viewing directly in Julius.
3. **Sample rather than slurp large datasets.**
   - For CSVs: sample initial rows using Python `pandas` with `nrows`.
   - For JSON/JSONL: use `jq` to inspect keys/structures.
   - For logs: use `tail` or `view_file` with line bounds.
4. **Hand off to dedicated skills** (e.g. `tamil-pdf`, `pdf-reading`, `docx`, `xlsx`, `pptx`) if advanced editing or custom processing is required.

---

## Tool Dispatch Table

| Extension                         | First move in Julius                                   | Dedicated skill / Tool |
| --------------------------------- | ----------------------------------------------------- | ---------------------- |
| `.pdf`                            | `view_file` or `pdfinfo` / `pdftotext`                | `pdf-reading`          |
| `.docx`                           | `extract-text` via `run_command`                      | `docx`                 |
| `.doc` (legacy)                   | Convert to `.docx` first                              | `docx`                 |
| `.xlsx`                           | `extract-text` or `openpyxl` (read_only=True)         | `xlsx`                 |
| `.xlsm`                           | `extract-text --format xlsx`                          | `xlsx`                 |
| `.xls` (legacy)                   | `pd.read_excel(engine="xlrd")`                        | `xlsx`                 |
| `.ods`                            | `pd.read_excel(engine="odf")`                         | `xlsx`                 |
| `.pptx`                           | `extract-text`                                        | `pptx`                 |
| `.ppt` (legacy)                   | Convert to `.pptx` first                              | `pptx`                 |
| `.csv`, `.tsv`                    | `pandas` with `nrows=5`                               | — (below)              |
| `.json`, `.jsonl`                 | `jq` for structure                                    | — (below)              |
| `.jpg`, `.png`, `.gif`, `.webp`   | `view_file` (vision) or PIL for programmatic processing| — (below)              |
| `.mp4`, `.mp3`, `.wav`            | `view_file` (media support)                           | —                      |
| `.zip`, `.tar`, `.tar.gz`         | `unzip -l` / `tar -tf` (List contents only)           | — (below)              |
| `.gz` (single file)               | `zcat \| head`                                        | — (below)              |
| `.epub`, `.odt`, `.rtf`, `.ipynb` | `extract-text`                                        | — (below)              |
| `.txt`, `.md`, `.log`, code files | `view_file` (with line ranges) or `grep_search`       | — (below)              |
| Unknown                           | `file /path/to/file` then decide                      | —                      |

---

## PDF Files

**Never** `cat` a PDF.

Quick first move in Julius — get page info or inspect fonts:

```bash
pdfinfo /path/to/document.pdf
pdffonts /path/to/document.pdf
```

- **Fonts listed** → standard PDF with extractable text layer:
  ```bash
  pdftotext -f 1 -l 1 /path/to/document.pdf - | head -20
  ```
- **No fonts listed** → scanned image PDF. Use OCR / page rasterization or consult `pdf-reading` skill.
- **Visual view**: In Julius, `view_file` can also render PDF content directly.

---

## DOCX / DOC

For quick text extraction:

```bash
extract-text /path/to/document.docx | head -200
```

For creation, editing, or tracked changes, consult the `docx` skill.

---

## XLSX / XLS / Spreadsheets

For a quick textual preview:

```bash
extract-text /path/to/data.xlsx | head -100
```

For structured preview in Python:

```python
from openpyxl import load_workbook
wb = load_workbook("/path/to/data.xlsx", read_only=True)
print("Sheets:", wb.sheetnames)
ws = wb.active
for row in ws.iter_rows(max_row=5, values_only=True):
    print(row)
```

- Legacy `.xls`: use `pd.read_excel("/path/to/old.xls", engine="xlrd", nrows=5)`
- OpenDocument `.ods`: use `pd.read_excel("/path/to/data.ods", engine="odf", nrows=5)`

---

## PPTX / Presentations

```bash
extract-text /path/to/deck.pptx | head -200
```

For detailed slide manipulations or creation, use the `pptx` skill.

---

## CSV / TSV

Avoid blindly printing huge CSVs. Preview using `pandas`:

```python
import pandas as pd
df = pd.read_csv("/path/to/data.csv", nrows=5)
print(df)
print(df.dtypes)
```

Approximate line count:

```bash
wc -l /path/to/data.csv
```

---

## JSON / JSONL

Inspect root structure first:

```bash
jq 'type' /path/to/data.json
jq 'if type == "array" then length elif type == "object" then keys else . end' /path/to/data.json
```

JSONL (line-delimited JSON):

```bash
head -3 /path/to/data.jsonl | jq .
wc -l /path/to/data.jsonl
```

---

## Images & Audio/Video Media

In Julius:
- Visual images and media files can be directly inspected using `view_file`.
- For programmatic processing, OCR, or metadata extraction:

```python
from PIL import Image
img = Image.open("/path/to/photo.jpg")
print(img.size, img.mode, img.format)
```

For OCR:
```python
import pytesseract
print(pytesseract.image_to_string(img))
```

---

## Archives (ZIP / TAR / TAR.GZ)

**List contents first, do NOT extract automatically.**

```bash
unzip -l /path/to/archive.zip
tar -tf /path/to/archive.tar.gz
```

Extract specific file on demand:
```bash
unzip -p /path/to/archive.zip relative/path/inside.txt
```

---

## Plain Text, Logs, and Source Code

In Julius:
1. Use `view_file` with `StartLine` and `EndLine` (view up to 800 lines at a time).
2. For searching terms across files: use `grep_search`.
3. For huge log files: use `tail -n 200 /path/to/app.log` via `run_command`.

---

## Unknown File Types

```bash
file /path/to/unknown.bin
xxd /path/to/unknown.bin | head -5
```
