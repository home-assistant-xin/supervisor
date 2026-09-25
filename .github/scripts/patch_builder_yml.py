#!/usr/bin/env python3
# ruff: noqa: T201
"""Patch .github/workflows/builder.yml for the home-assistant-xin fork.

Run this after syncing from upstream home-assistant/supervisor, before
pushing to home-assistant-xin/supervisor.  All fork-specific modifications
are applied here so that upstream merges stay conflict-free.

The script is idempotent: running it on an already-patched file is a no-op.

Changes applied:
1.  actions/helpers references → home-assistant-xin/actions/helpers (3 places)
2.  version job condition: repository_owner == 'home-assistant-xin'
3.  GHCR image addresses: ghcr.io/home-assistant-xin/...  (4 places)
4.  Delete "Build and publish wheels" step (requires WHEELS_KEY secret)
5.  "Build local wheels" condition: drop && publish == 'false'
6.  "Upload local wheels artifact" condition: drop && publish == 'false'
7.  Insert "Set source" step (patch_china_acceleration.py) in build and
    run_supervisor jobs if not already present.
"""
from __future__ import annotations

import sys
from pathlib import Path


def patch_actions_helpers(content: str) -> str:
    """Redirect home-assistant/actions/helpers → home-assistant-xin/actions/helpers."""
    old = "home-assistant/actions/helpers/"
    new = "home-assistant-xin/actions/helpers/"
    if old not in content:
        if new in content:
            print("SKIP: actions/helpers already patched")
            return content
        print("ERROR: cannot find actions/helpers references", file=sys.stderr)
        sys.exit(1)
    count = content.count(old)
    content = content.replace(old, new)
    print(f"OK: patched actions/helpers ({count} replacements)")
    return content


def patch_version_condition(content: str) -> str:
    """Change repository_owner check from home-assistant to home-assistant-xin."""
    old = "github.repository_owner == 'home-assistant' && needs.init.outputs.publish == 'true'"
    new = "github.repository_owner == 'home-assistant-xin' && needs.init.outputs.publish == 'true'"
    if old not in content:
        if new in content:
            print("SKIP: version condition already patched")
            return content
        print("ERROR: cannot find version repository_owner condition", file=sys.stderr)
        sys.exit(1)
    content = content.replace(old, new, 1)
    print("OK: patched version job repository_owner condition")
    return content


def patch_ghcr_addresses(content: str) -> str:
    """Replace ghcr.io/home-assistant/ → ghcr.io/home-assistant-xin/ in run_supervisor job."""
    old = "ghcr.io/home-assistant/amd64-hassio-supervisor"
    new = "ghcr.io/home-assistant-xin/amd64-hassio-supervisor"
    if old not in content:
        if new in content:
            print("SKIP: GHCR addresses already patched")
            return content
        print("ERROR: cannot find GHCR addresses", file=sys.stderr)
        sys.exit(1)
    count = content.count(old)
    content = content.replace(old, new)
    print(f"OK: patched GHCR addresses ({count} replacements)")
    return content


def patch_wheels_steps(content: str) -> str:
    """Delete 'Build and publish wheels' step and fix local wheels conditions."""
    publish_wheels_block = (
        "      - name: Build and publish wheels\n"
        "        if: needs.init.outputs.build_wheels == 'true' && needs.init.outputs.publish == 'true'\n"
        "        uses: home-assistant/wheels@"
    )
    if publish_wheels_block in content:
        idx = content.index(publish_wheels_block)
        block_start = content.rindex("\n", 0, idx) + 1
        next_step_marker = "\n      - name: "
        next_step = content.index(next_step_marker, idx)
        block_end = next_step + 1
        content = content[:block_start] + content[block_end:]
        print("OK: deleted 'Build and publish wheels' step")
    else:
        print("SKIP: 'Build and publish wheels' step already absent")

    old_cond = (
        "      - name: Build local wheels\n"
        "        if: needs.init.outputs.build_wheels == 'true' && needs.init.outputs.publish == 'false'\n"
    )
    new_cond = (
        "      - name: Build local wheels\n"
        "        if: needs.init.outputs.build_wheels == 'true'\n"
    )
    if old_cond in content:
        content = content.replace(old_cond, new_cond, 1)
        print("OK: patched 'Build local wheels' condition")
    elif new_cond in content:
        print("SKIP: 'Build local wheels' condition already patched")
    else:
        print("ERROR: cannot find 'Build local wheels' step", file=sys.stderr)
        sys.exit(1)

    old_cond = (
        "      - name: Upload local wheels artifact\n"
        "        if: needs.init.outputs.build_wheels == 'true' && needs.init.outputs.publish == 'false'\n"
    )
    new_cond = (
        "      - name: Upload local wheels artifact\n"
        "        if: needs.init.outputs.build_wheels == 'true'\n"
    )
    if old_cond in content:
        content = content.replace(old_cond, new_cond, 1)
        print("OK: patched 'Upload local wheels artifact' condition")
    elif new_cond in content:
        print("SKIP: 'Upload local wheels artifact' condition already patched")
    else:
        print("ERROR: cannot find 'Upload local wheels artifact' step", file=sys.stderr)
        sys.exit(1)
    return content


def patch_set_source_steps(content: str) -> str:
    """Insert 'Set source' step after Checkout in build and run_supervisor jobs."""
    set_source_block = (
        "\n"
        "      # Chinese source replacements\n"
        "      - name: Set source\n"
        "        run: |\n"
        "          python3 .github/scripts/patch_china_acceleration.py\n"
    )
    checkout_marker = (
        "      - name: Checkout the repository\n"
        "        uses: actions/checkout@"
    )
    patch_ref = "python3 .github/scripts/patch_china_acceleration.py"

    positions = []
    start = 0
    while True:
        pos = content.find(checkout_marker, start)
        if pos == -1:
            break
        positions.append(pos)
        start = pos + 1

    if len(positions) < 3:
        print(f"ERROR: expected >=3 checkout steps, found {len(positions)}", file=sys.stderr)
        sys.exit(1)

    build_checkout = positions[1]
    next_step = content.index("\n      - name: ", build_checkout + 1)
    if patch_ref in content[build_checkout : next_step + 200]:
        print("SKIP: 'Set source' already present in build job")
    else:
        content = content[:next_step] + set_source_block + content[next_step:]
        print("OK: inserted 'Set source' step in build job")

    rs_job_marker = "\n  run_supervisor:"
    rs_job_pos = content.index(rs_job_marker)
    rs_checkout = content.index(checkout_marker, rs_job_pos)
    next_step_rs = content.index("\n      - name: ", rs_checkout + 1)
    if patch_ref in content[rs_checkout : next_step_rs + 200]:
        print("SKIP: 'Set source' already present in run_supervisor job")
    else:
        content = content[:next_step_rs] + set_source_block + content[next_step_rs:]
        print("OK: inserted 'Set source' step in run_supervisor job")
    return content


def main() -> None:
    """Apply all fork-specific patches to builder.yml."""
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    filepath = root / ".github" / "workflows" / "builder.yml"

    if not filepath.exists():
        print(f"ERROR: {filepath} not found", file=sys.stderr)
        sys.exit(1)

    content = filepath.read_text(encoding="utf-8")
    content = patch_actions_helpers(content)
    content = patch_version_condition(content)
    content = patch_ghcr_addresses(content)
    content = patch_wheels_steps(content)
    content = patch_set_source_steps(content)
    filepath.write_text(content, encoding="utf-8")
    print(f"OK: patched {filepath}")


if __name__ == "__main__":
    main()
