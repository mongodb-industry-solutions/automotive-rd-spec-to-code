# score_cpp_policies

Centralized C++ quality tool policies for Eclipse S-CORE, providing sanitizer
configurations and clang-tidy integration reusable across all S-CORE modules
(logging, communication, baselibs, etc.).

Planned: clang-format, code coverage policies.

## What This Provides

- **[`sanitizers/`](sanitizers/README.md)** — ASan/UBSan/LSan/TSan Bazel `cc_feature`s, ready-to-use `--config=` aliases, suppression files, and `target_compatible_with` constraints.
- **[`clang_tidy/`](clang_tidy/README.md)** — centralized `.clang-tidy` baseline (conservative, tailorable per module) and a `--config=clang-tidy` Bazel integration.

## Sanitizers

| Config | Sanitizers | Notes |
|--------|-----------|-------|
| `--config=asan` | AddressSanitizer | Memory errors, buffer overflows |
| `--config=ubsan` | UndefinedBehaviorSanitizer | Integer overflow, null deref |
| `--config=lsan` | LeakSanitizer | Memory leaks |
| `--config=tsan` | ThreadSanitizer | Data races, deadlocks — cannot combine with ASan/LSan |
| `--config=asan_ubsan_lsan` | ASan + UBSan + LSan | **Recommended default for CI** |
| `--config=tsan_ubsan` | TSan + UBSan | Threading + undefined behavior |

## Sanitizer Combination Compatibility

| Combination | Valid? | Notes |
|---|---|---|
| ASan + UBSan | ✅ Yes | Standard — included in `--config=asan_ubsan_lsan` |
| ASan + LSan | ✅ Yes | Included in `--config=asan_ubsan_lsan` |
| TSan + UBSan | ✅ Yes | Use `--config=tsan_ubsan` |
| ASan + TSan | ❌ No | Incompatible runtime libraries (`libasan` vs `libtsan`) |
| LSan + TSan | ❌ No | TSan has built-in leak detection; enabling both causes runtime conflicts |

Invalid combinations are enforced at three layers, strongest first:

1. **Feature level (primary)** — the sanitizer `cc_feature`s declare
   `mutually_exclusive` categories (`asan_tsan`, `lsan_tsan`), so
   enabling `score_asan`+`score_tsan` or `score_lsan`+`score_tsan` through the
   toolchain fails at **analysis time** with an explicit error
   (`Symbol ...:asan_tsan is provided by all of the following features: score_asan score_tsan`).
   This protection is intrinsic to feature resolution and applies to every
   consumer automatically — no extra build-graph dependency required.
2. **Bazel build target (secondary)** — the
   `//sanitizers/flags:sanitizer_combination_check` genrule catches the
   flag-driven path and prints an actionable message. The CI test suite depends
   on it automatically.
3. **Compiler level (backstop)** — Clang emits an explicit error (e.g.
   `error: invalid argument '-fsanitize=address' combined with '-fsanitize=thread'`).

## Usage

### Add Dependency

```python
bazel_dep(name = "score_cpp_policies")
```

### Configure Sanitizers

Copy [`sanitizers/sanitizers.bazelrc`](sanitizers/sanitizers.bazelrc) into your repository's `.bazelrc`.

### Run Tests

```bash
bazel test --config=asan_ubsan_lsan //...   # recommended default for CI
```

See [`sanitizers/README.md`](sanitizers/README.md) for setup, the full config/constraint
reference, and the v0.x migration guide.

## Clang-Tidy

Centralized `.clang-tidy` check set and a `--config=clang-tidy` Bazel integration via
`aspect_rules_lint`.

See [`clang_tidy/README.md`](clang_tidy/README.md) for the 8-step setup guide.

## Testing This Repository

```bash
cd tests

bazel test --config=asan_ubsan_lsan //...
bazel test --config=tsan //...
bazel test --config=clang-tidy //...
```

## Contributing

See [CONTRIBUTION.md](CONTRIBUTION.md) for guidelines. All commits must follow [Eclipse Foundation commit rules](https://www.eclipse.org/projects/handbook/#resources-commit). Contributors must sign the ECA and DCO.

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.
