# Clang-Tidy

Centralized clang-tidy configuration for Eclipse S-CORE C++ modules.

## What This Provides

| File | Purpose |
|------|---------|
| `.clang-tidy` | Canonical S-CORE check set (conservative baseline, tailorable per module) |
| `clang_tidy.bazelrc` | Importable Bazel flags that activate the `clang-tidy` test config |

This module ships **policy assets**, not API wrappers. Consumers wire up
`lint_clang_tidy_aspect` / `lint_test` from `@aspect_rules_lint` directly —
exactly the same pattern used by the `sanitizers` module.

## Setup (8 steps)

### 1 — Add Bazel dependencies

In your `MODULE.bazel`:

```python
bazel_dep(name = "score_cpp_policies", version = "<version>")
bazel_dep(name = "aspect_rules_lint", version = "2.5.0")
bazel_dep(name = "toolchains_llvm",   version = "1.7.0")
```

Register an LLVM toolchain via the `llvm` extension (see `tests/MODULE.bazel` for a
minimal example).

### 2 — Import `clang_tidy.bazelrc`

In your workspace `.bazelrc`:

```bazelrc
import %workspace%/path/to/clang_tidy.bazelrc   # if vendored locally
# — or, once Bazel supports external-repo imports —
# import %workspace%/../clang_tidy/clang_tidy.bazelrc
```

> **Tip**: If your repo layout places `score_cpp_policies` as a sibling (as in the
> `tests/` self-test workspace here), a relative `import` works. Otherwise vendor
> the three lines from `clang_tidy.bazelrc` into your own `.bazelrc`.

### 3 — Create `tools/lint/BUILD.bazel`

```python
# tools/lint/BUILD.bazel  (empty package marker is sufficient)
```

### 4 — Create `tools/lint/linters.bzl`

```python
load("@aspect_rules_lint//lint:clang_tidy.bzl", "lint_clang_tidy_aspect")
load("@aspect_rules_lint//lint:lint_test.bzl",  "lint_test")

clang_tidy_aspect = lint_clang_tidy_aspect(
    binary  = Label("@llvm_toolchain//:clang-tidy"),
    configs = [
        Label("@score_cpp_policies//clang_tidy:.clang-tidy"),  # central baseline
        Label("//:.clang-tidy"),                               # local overrides (optional)
    ],
    lint_target_headers = True,
    angle_includes_are_system = True,
)

clang_tidy_test = lint_test(aspect = clang_tidy_aspect)
```

If you do not need per-module overrides, omit the `Label("//:.clang-tidy")` entry and
skip step 5.

### 5 — (Optional) Add a local `.clang-tidy` override

Place a `.clang-tidy` at your repo root to extend or tighten the central check set.
Use [`@score_cpp_policies//clang_tidy:.clang-tidy`](.clang-tidy) as the starting point.

> **Advisory checks**: Checks in the `cppcoreguidelines-*` and `modernize-*` families are
> advisory (warnings only). Only `clang-analyzer-*` is `WarningsAsErrors` by default.
> Module owners should tighten `WarningsAsErrors` incrementally as compliance improves.

### 6 — Expose `clang_tidy_test` in a `BUILD` file

```python
load("//tools/lint:linters.bzl", "clang_tidy_test")

clang_tidy_test(
    name = "clang_tidy",
    srcs = ["//..."],  # or a more targeted glob
)
```

### 7 — Run

```bash
bazel test --config=clang-tidy //...
```

Reports are written to `bazel-out/.../rules_lint_report/` as text files next to each
linted target.

### 8 — CI integration

Add a workflow job that runs:

```bash
bazel test --config=clang-tidy //...
```
