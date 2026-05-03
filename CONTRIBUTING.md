# Contributing

Thanks for considering a contribution. Three quick notes :

1. **Spec changes** belong in [`Lumencast/lumencast-protocol`](https://github.com/Lumencast/lumencast-protocol), not here. This repo implements the spec — it does not author it.

2. **Conformance** is the gate. Every change MUST keep the byte-level fixture suite and the cross-language scenario suite green. Run :

    ```sh
    uv sync --extra dev
    uv run pytest -m "not integration"   # unit + conformance fixtures
    uv run pytest -m integration          # spawn subprocess + interop self-test
    ```

3. **Style** is enforced by `ruff` (lint + format) and `mypy --strict`. CI rejects anything red. Run locally before pushing :

    ```sh
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy
    ```

## Workflow

- Fork → branch → PR. One concern per PR.
- Conventional commit titles preferred (`feat:`, `fix:`, `docs:`, etc.) but not enforced.
- All maintainer reviewers via `.github/CODEOWNERS`.

## Cross-language interop

If your change affects the wire format, the test control plane, or the conformance harness, run the cross-language matrix locally :

```sh
cd ../lumencast-protocol/interop
LUMENCAST_PY=$PWD/../../lumencast-py ./run-matrix.sh --server py --harness py
```

Open an interop issue against `lumencast-protocol` if a behaviour you depend on differs across SDKs.
