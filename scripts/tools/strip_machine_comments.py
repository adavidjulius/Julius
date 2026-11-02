#!/usr/bin/env python3
"""
Strips all machine-generated line-by-line comments across Julius repository.
Validates each modified file with AST (Python) or bash -n (Shell).
"""
import ast
import os
from pathlib import Path
import subprocess
import sys

MACHINE_PREFIXES_PY = [
    "# Execute statement:",
    "# Set ",
    "# Define function ",
    "# Define asynchronous coroutine method ",
    "# Loop through collection:",
    "# Repeat loop while condition is true:",
    "# Check condition:",
    "# Alternative condition branch:",
    "# Otherwise branch when previous conditions evaluate to false",
    "# Manage resource scope for:",
    "# Output message to console:",
    "# Asynchronously invoke:",
    "# Return value ",
    "# Return value to caller",
    "# Import ",
    "# Enable modern Python type hint annotations support across versions",
    "# Enable modern Python type annotations",
    "# Tell the operating system shell to run this script using Python 3",
    "# Docstring documentation block",
    "# Check if count is odd to toggle multiline string state",
    "# If inside a multiline string block or line is blank or already a comment",
    "# If previous line had a backslash line continuation, don't break continuation with comment",
    "# If previous line was already a comment, avoid duplicate commentary",
    "# Determine indentation",
    "# AST validation: ensure the annotated code is 100% syntactically valid Python",
    "# If adding comments caused a syntax error",
    "# Function to annotate an entire file with line-by-line comments",
    "# Handle triple double-quote docstrings/strings",
    "# Handle triple single-quote docstrings/strings",
    "# Catch exception of type",
    "# Catch any unhandled runtime exception",
    "# Execute cleanup block unconditionally",
    "# Yield value ",
    "# Asynchronously pause execution for",
    "# Asynchronously execute coroutine",
    "# Do nothing and continue execution (placeholder statement)",
    "# Break out of current loop",
    "# Skip remainder of current iteration and continue to next loop cycle",
    "# Raise exception ",
    "# Assert that condition holds true:",
    "# Create dedicated logger instance for",
    "# Decorate class as a dataclass",
    "# Decorate method as a getter property",
    "# Decorate method as static",
    "# Decorate method as classmethod",
    "# Decorate function as a pytest fixture",
    "# Define class ",
    "# Check if this script is being executed directly from the terminal",
    "# Begin protected try-block to catch and handle runtime exceptions",
]

MACHINE_PREFIXES_JS = [
    "// Execute statement:",
    "// Render Ink terminal ",
    "// Render interactive user prompt ",
    "// Render bottom status bar ",
    "// Render floating toast notification ",
    "// Render animated thinking ",
    "// Render tool execution summary ",
    "// Render AI assistant reply ",
    "// Render user message entry ",
    "// Render Julius welcome ",
    "// Render command suggestion ",
    "// Render interactive model selector ",
    "// Render help and keyboard shortcut ",
    "// Render code diff review ",
    "// Render background action monitor ",
    "// Render user confirmation prompt ",
    "// Render interactive user question ",
    "// Import React and React hooks",
    "// Import React library core framework",
    "// Import TypeScript type definitions",
    "// Import symbols",
    "// Import default export",
    "// Import side-effect module",
    "// Export TypeScript interface definition",
    "// Export TypeScript type alias",
    "// Define TypeScript interface contract",
    "// Define TypeScript type alias",
    "// Export constant definition",
    "// Export function",
    "// Export asynchronous function",
    "// Export default module member",
    "// Declare reactive state",
    "// Create persistent reference",
    "// Register component side-effect lifecycle hook",
    "// Define constant",
    "// Declare variable",
    "// Define asynchronous function",
    "// Define function",
    "// Define optional property",
    "// Define property",
    "// Check condition:",
    "// Alternative condition check:",
    "// Execute fallback branch when conditions evaluate to false",
    "// Return rendered JSX layout tree to caller",
    "// Return value",
    "// Return early from function",
    "// Begin protected try block for runtime error handling",
    "// Catch and handle runtime exception",
    "// Catch and handle runtime error",
    "// Execute cleanup logic in finally block",
    "// Branch execution flow based on expression:",
    "// Match switch case value:",
    "// Default fallback switch branch",
    "// Break out of current control structure",
    "// Skip to next loop iteration",
    "// Throw runtime error exception:",
    "// Log diagnostic message to console:",
    "// Log error message to console:",
    "// Log warning message to console:",
    "// Asynchronously await promise resolution:",
    "// Set ",
]

MACHINE_PREFIXES_SH = [
    "# Set and export environment variable",
    "# Assign local variable",
    "# Change working directory to",
    "# Create directory structure if it does not already exist:",
    "# Force remove target file or directory tree:",
    "# Remove target file if present:",
    "# Force copy file:",
    "# Copy source file to target:",
    "# Move or rename file:",
]

root = Path(__file__).resolve().parent.parent
ignore_dirs = {".git", ".venv", "node_modules", "dist", "build", "__pycache__"}

py_files_cleaned = 0
py_lines_removed = 0
js_files_cleaned = 0
js_lines_removed = 0
sh_files_cleaned = 0
sh_lines_removed = 0

# 1. Clean Python files
for p in root.rglob("*.py"):
    if any(part in ignore_dirs for part in p.parts):
        continue
    try:
        content = p.read_text(encoding="utf-8")
    except Exception:
        continue

    lines = content.splitlines()
    out = []
    in_triple_double = False
    in_triple_single = False
    removed = 0

    for line in lines:
        stripped = line.strip()
        if '"""' in line and line.count('"""') % 2 == 1:
            in_triple_double = not in_triple_double
        if "'''" in line and line.count("'''") % 2 == 1:
            in_triple_single = not in_triple_single

        if not in_triple_double and not in_triple_single:
            if any(stripped.startswith(pr) for pr in MACHINE_PREFIXES_PY):
                removed += 1
                continue
        out.append(line)

    if removed > 0:
        cleaned_content = "\n".join(out) + "\n"
        try:
            ast.parse(cleaned_content, filename=str(p))
            p.write_text(cleaned_content, encoding="utf-8")
            py_files_cleaned += 1
            py_lines_removed += removed
        except SyntaxError as e:
            print(f"⚠️ SyntaxError on {p} when cleaning: {e}")

# 2. Clean JS/TS/TSX files
for p in root.rglob("*"):
    if any(part in ignore_dirs for part in p.parts):
        continue
    if p.suffix not in (".ts", ".tsx", ".js", ".cjs", ".mjs"):
        continue
    try:
        content = p.read_text(encoding="utf-8")
    except Exception:
        continue

    lines = content.splitlines()
    out = []
    in_backtick = False
    removed = 0

    for line in lines:
        stripped = line.strip()
        # Track multiline template strings
        if '`' in line and line.count('`') % 2 == 1:
            in_backtick = not in_backtick

        if not in_backtick:
            if any(stripped.startswith(pr) for pr in MACHINE_PREFIXES_JS):
                removed += 1
                continue
        out.append(line)

    if removed > 0:
        cleaned_content = "\n".join(out) + "\n"
        p.write_text(cleaned_content, encoding="utf-8")
        js_files_cleaned += 1
        js_lines_removed += removed

# 3. Clean Shell files
for p in root.rglob("*.sh"):
    if any(part in ignore_dirs for part in p.parts):
        continue
    try:
        content = p.read_text(encoding="utf-8")
    except Exception:
        continue

    lines = content.splitlines()
    out = []
    removed = 0

    for line in lines:
        stripped = line.strip()
        if any(stripped.startswith(pr) for pr in MACHINE_PREFIXES_SH):
            removed += 1
            continue
        out.append(line)

    if removed > 0:
        cleaned_content = "\n".join(out) + "\n"
        res = subprocess.run(["bash", "-n"], input=cleaned_content, text=True, capture_output=True)
        if res.returncode == 0:
            p.write_text(cleaned_content, encoding="utf-8")
            sh_files_cleaned += 1
            sh_lines_removed += removed
        else:
            print(f"⚠️ bash -n failed on {p}")

print("==========================================")
print(f"✅ Python: {py_files_cleaned} files cleaned, {py_lines_removed} machine comment lines removed.")
print(f"✅ JS/TS: {js_files_cleaned} files cleaned, {js_lines_removed} machine comment lines removed.")
print(f"✅ Shell: {sh_files_cleaned} files cleaned, {sh_lines_removed} machine comment lines removed.")
print(f"🎉 TOTAL: {py_files_cleaned + js_files_cleaned + sh_files_cleaned} files cleaned, {py_lines_removed + js_lines_removed + sh_lines_removed} machine comment lines removed.")
print("==========================================")
