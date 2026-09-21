# bettie-dog/sapling fork delta

This fork tracks facebook/sapling and is synced by merging upstream `main`.
This file is the manifest of every logical patch the fork carries, so that
a merge conflict during a sync maps to a named patch instead of archaeology.
Update it in the same commit that adds, changes, or upstreams a patch.

## Sync protocol

1. `sl pull upstream`, then `sl merge <upstream tip>` on `main`.
2. Resolve conflicts using the patch list below; prefer taking upstream
   verbatim wherever a patch has been obsoleted (delete its entry here).
3. Build (`make -C eden/scm oss`) and run
   `cd eden/scm/tests && ../out/sl debugruntest test-ext-github*.t`.
4. Commit the merge and push to `main`.

## Patches

### Native GitHub stacked pull requests (`github.pr-workflow=stack`)

The fork's main feature: `sl pr submit` links single-workflow pull
requests into GitHub's native stacked pull requests (public preview),
with automatic reconciliation and `--rebuild-stack` for destructive
changes (reorders, drops, fork switches).

- Fork-owned files (never conflict): `eden/scm/sapling/ext/github/native_stacks.py`,
  `eden/scm/tests/github/mock_stack_*.py`,
  `eden/scm/tests/test-ext-github-pr-submit-stack.t`.
- Touch points in upstream files: `ext/github/__init__.py` (submit flag),
  `ext/github/submit.py` (SubmitWorkflow.STACK, call sites),
  `ext/github/gh_submit.py` (base-optional update_pull_request),
  `ext/github/consts/query.py` (no-base update mutation),
  `ext/github/pull_request_body.py` (stack_footer flag),
  `ext/github/mock_utils.py` (stack expectations),
  `eden/scm/tests/default_hgrc.py` (old-version hint ack),
  `website/docs/git/sapling-stack.md` (workflow docs).
- Upstream status: not upstreamed. A parallel upstream effort exists
  (facebook/sapling#1392–#1398, different design); revisit after it
  lands or stalls.

### wezterm-dynamic version pins

Upstream's generated manifests declare `wezterm-dynamic` without a
version, which plain cargo rejects. Pinned `version = "0.2.1"` in:
`eden/scm/lib/io/Cargo.toml`, `eden/scm/lib/io/term/style/Cargo.toml`,
`eden/scm/lib/progress/render/Cargo.toml`,
`eden/scm/lib/third-party/streampager/Cargo.toml`,
`eden/scm/saplingnative/bindings/modules/pytermwiz/Cargo.toml`.

- Upstream status: upstream bug (autocargo output); expected to recur or
  conflict on syncs until fixed upstream. Drop the pins the moment
  upstream manifests carry a version again.

### xz manifest bump

`build/fbcode_builder/manifests/xz`: 5.2.5 → 5.8.3, fetched from GitHub
releases (tukaani.org rate-limits cloud IPs).

- Upstream status: upstreamable, not sent yet.

### Fork CI

`.github/workflows/`: manual dispatch + longer timeouts for the
sapling-cli and mononoke builds, macos-15 runner for the homebrew
release, manylinux image pulled from facebook/sapling's GHCR, explicit
`contents: write` on release workflows.

- Upstream status: fork-only, permanent.

### Local tooling

`.gitignore`: ignores `.claude/local.md` (machine-local notes).
`FORK.md`: this file.

- Upstream status: fork-only, permanent.
