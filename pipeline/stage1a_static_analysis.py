#!/usr/bin/env python3
"""
Stage 1a: Static Analysis for Thread Discovery

Tree-sitter based static analyzer that exhaustively finds all thread creation
and naming sites in C/C++ source code. Deterministic, complete, free.

Extracts 4 pattern types:
  1. pthread_setname_np(handle, name) — thread naming API
  2. prctl(PR_SET_NAME, name) — alternative thread naming
  3. pthread_create(&t, attr, start_routine, arg) — thread creation
  4. std::thread / port::Thread construction — C++ thread creation

Also finds macro wrappers (e.g., redis_set_thread_title) that expand to
pthread_setname_np, and traces their call sites.

Usage:
  python3 stage1a_static_analysis.py <source_path> <language> [--json]

Output: ThreadReport JSON to stdout.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import tree_sitter
import tree_sitter_c
import tree_sitter_cpp


# File extensions per language
EXTENSIONS = {
    "c": {".c", ".h"},
    "cpp": {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"},
}

# Directories to skip (build artifacts, tests, third-party deps, etc.)
SKIP_DIRS = {
    ".git", "build", "cmake-build", "third-party", "third_party",
    "doc", "docs", "documentation", "examples", "samples",
    "__pycache__", "node_modules", ".cache",
}

# Max context lines to capture around each finding
CONTEXT_LINES = 5


def get_parser(language):
    """Create a tree-sitter parser for the given language."""
    if language == "c":
        lang = tree_sitter.Language(tree_sitter_c.language())
    elif language == "cpp":
        lang = tree_sitter.Language(tree_sitter_cpp.language())
    else:
        raise ValueError(f"Unsupported language: {language}")
    return tree_sitter.Parser(lang), lang


def collect_source_files(source_path, language):
    """Collect all source files matching the language extensions."""
    exts = EXTENSIONS.get(language, EXTENSIONS["cpp"])
    files = []
    source = Path(source_path).resolve()
    for root, dirs, filenames in os.walk(source):
        # Prune skipped directories
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in filenames:
            if Path(fname).suffix in exts:
                files.append(os.path.join(root, fname))
    files.sort()
    return files


def get_context_snippet(source_lines, line_num, context=CONTEXT_LINES):
    """Extract context lines around a line number (1-indexed)."""
    start = max(0, line_num - 1 - context)
    end = min(len(source_lines), line_num + context)
    lines = source_lines[start:end]
    return "\n".join(lines)


def extract_string_literal(node):
    """Extract the value from a string_literal node, stripping quotes."""
    text = node.text.decode()
    if text.startswith('"') and text.endswith('"'):
        return text[1:-1]
    return text


def find_call_expressions(root_node, lang, language):
    """Find all call expressions in the AST using tree-sitter queries."""
    results = []

    # Query for unqualified function calls: func(args)
    q1 = tree_sitter.Query(lang, """
    (call_expression
      function: (identifier) @func
      arguments: (argument_list) @args)
    """)
    cursor1 = tree_sitter.QueryCursor(q1)
    for _, captures in cursor1.matches(root_node):
        func_node = captures["func"][0]
        args_node = captures["args"][0]
        results.append(("call", func_node, args_node))

    # C++-only queries (qualified_identifier and field_expression exist only in C++ grammar)
    if language == "cpp":
        # Query for qualified function calls: ns::func(args)
        q2 = tree_sitter.Query(lang, """
        (call_expression
          function: (qualified_identifier) @func
          arguments: (argument_list) @args)
        """)
        cursor2 = tree_sitter.QueryCursor(q2)
        for _, captures in cursor2.matches(root_node):
            func_node = captures["func"][0]
            args_node = captures["args"][0]
            results.append(("qualified_call", func_node, args_node))

        # Query for method calls: obj.method(args) / obj->method(args)
        q3 = tree_sitter.Query(lang, """
        (call_expression
          function: (field_expression) @func
          arguments: (argument_list) @args)
        """)
        cursor3 = tree_sitter.QueryCursor(q3)
        for _, captures in cursor3.matches(root_node):
            func_node = captures["func"][0]
            args_node = captures["args"][0]
            results.append(("method_call", func_node, args_node))

    return results


def analyze_args(args_node):
    """Extract individual arguments from an argument_list node."""
    args = []
    for child in args_node.children:
        if child.type not in ("(", ")", ","):
            args.append(child)
    return args


def is_string_literal(node):
    """Check if a node is a string literal."""
    return node.type in ("string_literal", "string_content",
                          "concatenated_string")


def extract_arg_text(node):
    """Extract a readable representation of an argument node."""
    text = node.text.decode()
    # Truncate very long expressions
    if len(text) > 120:
        text = text[:117] + "..."
    return text


def find_macro_wrappers(source_text):
    """Find #define macros that wrap pthread_setname_np or prctl(PR_SET_NAME).

    Returns a dict mapping macro name -> underlying function.
    """
    macros = {}
    for line in source_text.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("#define"):
            continue
        # e.g. #define redis_set_thread_title(name) pthread_setname_np(...)
        if "pthread_setname_np" in stripped or "prctl" in stripped:
            parts = stripped.split(None, 2)  # #define NAME(args) body
            if len(parts) >= 2:
                macro_name = parts[1].split("(")[0]
                if macro_name and macro_name != "pthread_setname_np":
                    if "pthread_setname_np" in stripped:
                        macros[macro_name] = "pthread_setname_np"
                    elif "PR_SET_NAME" in stripped:
                        macros[macro_name] = "prctl"
    return macros


def find_proc_title_setters(source_text, source_lines):
    """Find functions that wrap setproctitle() and could set process comm.

    On Linux, forked child processes inherit the parent's comm but often call
    setproctitle() to change it. These show up as different names in
    /proc/pid/comm. Returns a dict: function_name -> "setproctitle".
    """
    setters = {}
    # Look for functions that call setproctitle and take a string title arg
    # Pattern: function definition containing setproctitle call
    in_function = None
    brace_depth = 0
    has_setproctitle = False

    for i, line in enumerate(source_lines):
        # Simple function definition detection
        func_match = re.match(
            r'^(?:int|void|static\s+(?:int|void))\s+(\w+)\s*\(', line)
        if func_match and brace_depth == 0:
            in_function = func_match.group(1)
            has_setproctitle = False

        brace_depth += line.count("{") - line.count("}")

        if "setproctitle" in line and in_function:
            has_setproctitle = True

        if brace_depth == 0 and in_function:
            if has_setproctitle and in_function not in ("setproctitle",):
                setters[in_function] = "setproctitle"
            in_function = None
            has_setproctitle = False

    return setters


def regex_find_thread_names(source_text, source_lines, rel_path, macro_wrappers):
    """Regex-based fallback to find thread naming calls that tree-sitter misses.

    Tree-sitter can fail to parse calls inside preprocessor-guarded blocks or
    with GNU __attribute__ extensions. This function catches those cases.
    Returns a list of thread_name entries.
    """
    results = []

    # Pattern 1: pthread_setname_np(anything, name_arg)
    for m in re.finditer(
        r'pthread_setname_np\s*\(\s*([^,]+)\s*,\s*(.+?)\s*\)\s*;', source_text
    ):
        line = source_text[:m.start()].count("\n") + 1
        name_arg_text = m.group(2).strip()
        # Check if it's a string literal
        str_match = re.match(r'^"([^"]*)"$', name_arg_text)
        is_const = str_match is not None
        const_val = str_match.group(1) if str_match else None
        context = get_context_snippet(source_lines, line)
        results.append({
            "file": rel_path,
            "line": line,
            "function": "pthread_setname_np",
            "name_arg": name_arg_text,
            "is_constant": is_const,
            "constant_value": const_val,
            "context_snippet": context,
        })

    # Pattern 2: prctl(PR_SET_NAME, name_arg)
    for m in re.finditer(
        r'prctl\s*\(\s*PR_SET_NAME\s*,\s*(.+?)\s*\)\s*;', source_text
    ):
        line = source_text[:m.start()].count("\n") + 1
        name_arg_text = m.group(1).strip()
        str_match = re.match(r'^"([^"]*)"$', name_arg_text)
        is_const = str_match is not None
        const_val = str_match.group(1) if str_match else None
        context = get_context_snippet(source_lines, line)
        results.append({
            "file": rel_path,
            "line": line,
            "function": "prctl(PR_SET_NAME)",
            "name_arg": name_arg_text,
            "is_constant": is_const,
            "constant_value": const_val,
            "context_snippet": context,
        })

    # Pattern 3: macro wrappers like redis_set_thread_title(name)
    for macro_name, underlying in macro_wrappers.items():
        pattern = re.escape(macro_name) + r'\s*\(\s*(.+?)\s*\)\s*;'
        for m in re.finditer(pattern, source_text):
            line = source_text[:m.start()].count("\n") + 1
            name_arg_text = m.group(1).strip()
            str_match = re.match(r'^"([^"]*)"$', name_arg_text)
            is_const = str_match is not None
            const_val = str_match.group(1) if str_match else None
            context = get_context_snippet(source_lines, line)
            results.append({
                "file": rel_path,
                "line": line,
                "function": f"{macro_name} (macro for {underlying})",
                "name_arg": name_arg_text,
                "is_constant": is_const,
                "constant_value": const_val,
                "context_snippet": context,
            })

    return results


def analyze_file(filepath, parser, lang, language, source_path_base,
                  macro_wrappers, proc_title_setters):
    """Analyze a single source file for thread creation/naming patterns."""
    thread_names = []
    thread_creates = []

    try:
        with open(filepath, "rb") as f:
            source_bytes = f.read()
    except (OSError, IOError):
        return thread_names, thread_creates

    source_text = source_bytes.decode("utf-8", errors="replace")
    source_lines = source_text.split("\n")

    # Check for macro wrappers defined in this file
    file_macros = find_macro_wrappers(source_text)
    macro_wrappers.update(file_macros)

    # Check for proc title setter functions defined in this file
    file_setters = find_proc_title_setters(source_text, source_lines)
    proc_title_setters.update(file_setters)

    tree = parser.parse(source_bytes)
    calls = find_call_expressions(tree.root_node, lang, language)

    rel_path = os.path.relpath(filepath, source_path_base)

    for call_type, func_node, args_node in calls:
        func_name = func_node.text.decode()
        line = func_node.start_point[0] + 1
        args = analyze_args(args_node)
        context = get_context_snippet(source_lines, line)

        # --- pthread_setname_np(handle, name) ---
        if func_name == "pthread_setname_np" or func_name.endswith("::pthread_setname_np"):
            name_arg = args[1] if len(args) >= 2 else (args[0] if args else None)
            if name_arg:
                is_const = is_string_literal(name_arg)
                const_val = extract_string_literal(name_arg) if is_const else None
                thread_names.append({
                    "file": rel_path,
                    "line": line,
                    "function": "pthread_setname_np",
                    "name_arg": extract_arg_text(name_arg),
                    "is_constant": is_const,
                    "constant_value": const_val,
                    "context_snippet": context,
                })

        # --- prctl(PR_SET_NAME, name) ---
        elif func_name == "prctl":
            if len(args) >= 2:
                first_arg = args[0].text.decode()
                if "PR_SET_NAME" in first_arg:
                    name_arg = args[1]
                    is_const = is_string_literal(name_arg)
                    const_val = extract_string_literal(name_arg) if is_const else None
                    thread_names.append({
                        "file": rel_path,
                        "line": line,
                        "function": "prctl(PR_SET_NAME)",
                        "name_arg": extract_arg_text(name_arg),
                        "is_constant": is_const,
                        "constant_value": const_val,
                        "context_snippet": context,
                    })

        # --- Macro wrappers (e.g., redis_set_thread_title) ---
        elif func_name in macro_wrappers:
            underlying = macro_wrappers[func_name]
            if args:
                name_arg = args[0]
                is_const = is_string_literal(name_arg)
                const_val = extract_string_literal(name_arg) if is_const else None
                thread_names.append({
                    "file": rel_path,
                    "line": line,
                    "function": f"{func_name} (macro for {underlying})",
                    "name_arg": extract_arg_text(name_arg),
                    "is_constant": is_const,
                    "constant_value": const_val,
                    "context_snippet": context,
                })

        # --- Process title setters (e.g., redisSetProcTitle) ---
        elif func_name in proc_title_setters:
            if args:
                name_arg = args[0]
                is_const = is_string_literal(name_arg)
                const_val = extract_string_literal(name_arg) if is_const else None
                # Only include calls with actual title arguments (not NULL)
                arg_text = extract_arg_text(name_arg)
                if arg_text != "NULL" and arg_text != "0":
                    thread_names.append({
                        "file": rel_path,
                        "line": line,
                        "function": f"{func_name} (sets process title)",
                        "name_arg": arg_text,
                        "is_constant": is_const,
                        "constant_value": const_val,
                        "context_snippet": context,
                    })

        # --- pthread_create(&tid, attr, start_routine, arg) ---
        elif func_name == "pthread_create":
            if len(args) >= 3:
                start_routine = extract_arg_text(args[2])
                thread_creates.append({
                    "file": rel_path,
                    "line": line,
                    "method": "pthread_create",
                    "start_routine": start_routine,
                    "context_snippet": context,
                })

        # --- Qualified calls: std::thread(...), port::Thread(...) ---
        elif call_type == "qualified_call":
            parts = func_name.split("::")
            last_part = parts[-1].lower() if parts else ""
            if last_part == "thread" or last_part == "jthread":
                start_routine = extract_arg_text(args[0]) if args else "unknown"
                thread_creates.append({
                    "file": rel_path,
                    "line": line,
                    "method": func_name,
                    "start_routine": start_routine,
                    "context_snippet": context,
                })

        # --- Method calls: threads_.emplace_back(...) etc. ---
        elif call_type == "method_call":
            method = func_name.split(".")[-1] if "." in func_name else func_name
            if method in ("emplace_back", "push_back"):
                # Check if first arg looks like a function/callable
                if args and args[0].type == "identifier":
                    # Could be thread creation via vector.emplace_back(func, ...)
                    # Only include if the function name suggests thread work
                    start_routine = extract_arg_text(args[0])
                    # Heuristic: common thread wrapper names
                    if any(kw in start_routine.lower() for kw in
                           ("thread", "worker", "bg", "background", "handler",
                            "routine", "task", "run")):
                        thread_creates.append({
                            "file": rel_path,
                            "line": line,
                            "method": func_name,
                            "start_routine": start_routine,
                            "context_snippet": context,
                        })

    # --- Declaration-based std::thread construction (C++ only) ---
    # std::thread t(func, args...) parses as a declaration, not a call
    if language == "cpp":
        q_decl = tree_sitter.Query(lang, """
        (declaration
          type: (qualified_identifier) @type_name
          declarator: (function_declarator
            declarator: (identifier) @var_name
            parameters: (parameter_list) @params))
        """)
        cursor_decl = tree_sitter.QueryCursor(q_decl)
        for _, captures in cursor_decl.matches(tree.root_node):
            type_name = captures["type_name"][0].text.decode()
            params = captures["params"][0]
            line = captures["type_name"][0].start_point[0] + 1

            parts = type_name.split("::")
            last = parts[-1].lower() if parts else ""
            if last in ("thread", "jthread"):
                param_children = [c for c in params.children
                                  if c.type not in ("(", ")", ",")]
                start_routine = (extract_arg_text(param_children[0])
                                 if param_children else "unknown")
                context = get_context_snippet(source_lines, line)
                thread_creates.append({
                    "file": rel_path,
                    "line": line,
                    "method": type_name + " (declaration)",
                    "start_routine": start_routine,
                    "context_snippet": context,
                })

    # Regex fallback: catch thread naming calls that tree-sitter missed
    # (e.g., inside preprocessor-guarded blocks with __attribute__)
    regex_names = regex_find_thread_names(source_text, source_lines,
                                          rel_path, macro_wrappers)
    ts_lines = {(e["file"], e["line"]) for e in thread_names}
    for entry in regex_names:
        key = (entry["file"], entry["line"])
        if key not in ts_lines:
            thread_names.append(entry)

    return thread_names, thread_creates


def analyze(source_path, language):
    """Run static analysis on a source tree.

    Returns a ThreadReport dict.
    """
    source_path = os.path.abspath(source_path)
    files = collect_source_files(source_path, language)

    if not files:
        print(f"Warning: no {language} source files found in {source_path}",
              file=sys.stderr)

    parser, lang = get_parser(language)

    all_thread_names = []
    all_thread_creates = []
    macro_wrappers = {}  # Accumulated across all files
    proc_title_setters = {}  # Functions that wrap setproctitle()
    files_analyzed = 0
    files_with_findings = 0

    # First pass: scan all files for macro definitions and proc title setters
    for filepath in files:
        try:
            with open(filepath) as f:
                text = f.read()
            macros = find_macro_wrappers(text)
            macro_wrappers.update(macros)
            setters = find_proc_title_setters(text, text.split("\n"))
            proc_title_setters.update(setters)
        except (OSError, IOError):
            continue

    # Second pass: analyze all files
    for filepath in files:
        names, creates = analyze_file(filepath, parser, lang, language,
                                      source_path, macro_wrappers,
                                      proc_title_setters)
        files_analyzed += 1
        if names or creates:
            files_with_findings += 1
        all_thread_names.extend(names)
        all_thread_creates.extend(creates)

    # Deduplicate: same file+line should only appear once
    seen_names = set()
    deduped_names = []
    for entry in all_thread_names:
        key = (entry["file"], entry["line"])
        if key not in seen_names:
            seen_names.add(key)
            deduped_names.append(entry)

    seen_creates = set()
    deduped_creates = []
    for entry in all_thread_creates:
        key = (entry["file"], entry["line"])
        if key not in seen_creates:
            seen_creates.add(key)
            deduped_creates.append(entry)

    report = {
        "source_path": source_path,
        "language": language,
        "files_analyzed": files_analyzed,
        "files_with_findings": files_with_findings,
        "macro_wrappers": macro_wrappers,
        "proc_title_setters": proc_title_setters,
        "thread_names": deduped_names,
        "thread_creates": deduped_creates,
    }

    return report


def print_summary(report, file=sys.stderr):
    """Print a human-readable summary of the analysis."""
    print(f"\n=== Stage 1a: Static Analysis Report ===", file=file)
    print(f"Source: {report['source_path']}", file=file)
    print(f"Language: {report['language']}", file=file)
    print(f"Files analyzed: {report['files_analyzed']}", file=file)
    print(f"Files with findings: {report['files_with_findings']}", file=file)

    if report["macro_wrappers"]:
        print(f"\nMacro wrappers found:", file=file)
        for name, underlying in report["macro_wrappers"].items():
            print(f"  {name} -> {underlying}", file=file)

    if report.get("proc_title_setters"):
        print(f"\nProcess title setters found:", file=file)
        for name, underlying in report["proc_title_setters"].items():
            print(f"  {name} -> {underlying}", file=file)

    print(f"\nThread naming sites ({len(report['thread_names'])}):", file=file)
    for entry in report["thread_names"]:
        const_info = f" = \"{entry['constant_value']}\"" if entry["is_constant"] else ""
        print(f"  {entry['file']}:{entry['line']}  "
              f"{entry['function']}({entry['name_arg']}){const_info}",
              file=file)

    print(f"\nThread creation sites ({len(report['thread_creates'])}):", file=file)
    for entry in report["thread_creates"]:
        print(f"  {entry['file']}:{entry['line']}  "
              f"{entry['method']} -> {entry['start_routine']}",
              file=file)


def main():
    parser = argparse.ArgumentParser(
        description="Stage 1a: Static analysis for thread discovery")
    parser.add_argument("source_path", help="Path to application source code")
    parser.add_argument("language", choices=["c", "cpp"],
                        help="Primary language (c or cpp)")
    parser.add_argument("--json", action="store_true", default=True,
                        help="Output JSON to stdout (default)")
    parser.add_argument("--summary", action="store_true",
                        help="Print human-readable summary to stderr")

    args = parser.parse_args()

    if not os.path.isdir(args.source_path):
        print(f"Error: {args.source_path} is not a directory", file=sys.stderr)
        sys.exit(1)

    report = analyze(args.source_path, args.language)

    if args.summary:
        print_summary(report)

    # Always output JSON to stdout
    json.dump(report, sys.stdout, indent=2)
    print()  # trailing newline


if __name__ == "__main__":
    main()
