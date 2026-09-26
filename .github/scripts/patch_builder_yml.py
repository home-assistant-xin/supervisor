#!/usr/bin/env python3
# ruff: noqa: T201
"""Patch .github/workflows/builder.yml for the home-assistant-xin fork.

Run this after syncing from upstream home-assistant/supervisor, before
pushing to home-assistant-xin/supervisor.  All fork-specific modifications
are applied here so that upstream merges stay conflict-free.

The script is idempotent: running it on an already-patched file is a no-op.

Changes applied:
1.  actions/helpers references → home-assistant-xin/actions/helpers (3 places)
2.  Delete push trigger condition (no auto dev builds on push)
3.  Delete "Build and publish wheels" step (requires WHEELS_KEY secret)
4.  "Build local wheels" condition: drop && publish == 'false'
5.  "Upload local wheels artifact" condition: drop && publish == 'false'
6.  Insert "Set source" step in build job after checkout
7.  version job condition: repository_owner == 'home-assistant-xin'
8.  GHCR image addresses: ghcr.io/home-assistant-xin/...  (4 places)
9.  Insert "Set source" step in run_supervisor job after checkout
"""
from __future__ import annotations

from pathlib import Path
import sys


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


def patch_delete_push_trigger(content: str) -> str:
    """Delete the push: trigger condition."""
    push_block = (
        "  push:\n"
        "    branches: [\"main\"]\n"
        "    paths:\n"
    )
    if push_block not in content:
        if "  push:\n    branches:" not in content:
            print("SKIP: push trigger already absent")
            return content
        print("ERROR: push trigger found but format differs", file=sys.stderr)
        sys.exit(1)

    idx = content.index(push_block)
    block_start = content.rindex("\n", 0, idx) + 1

    next_job_marker = "\n\nenv:"
    if next_job_marker not in content[idx:]:
        next_job_marker = "\nenv:"
    block_end = content.index(next_job_marker, idx)

    content = content[:block_start] + content[block_end + 1:]
    print("OK: deleted push trigger condition")
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


def _insert_set_source(content: str, checkout_pos: int, label: str) -> str:
    """Insert 'Set source' step after a checkout position if not already present."""
    set_source_block = (
        "\n"
        "      # Chinese source replacements\n"
        "      - name: Set source\n"
        "        run: |\n"
        "          python3 .github/scripts/patch_china_acceleration.py\n"
    )
    patch_ref = "python3 .github/scripts/patch_china_acceleration.py"
    next_step = content.index("\n      - name: ", checkout_pos + 1)
    if patch_ref in content[checkout_pos : next_step + 200]:
        print(f"SKIP: 'Set source' already present in {label}")
        return content
    content = content[:next_step] + set_source_block + content[next_step:]
    print(f"OK: inserted 'Set source' step in {label}")
    return content


def patch_set_source_steps(content: str) -> str:
    """Insert 'Set source' step in build and run_supervisor jobs."""
    checkout_marker = (
        "      - name: Checkout the repository\n"
        "        uses: actions/checkout@"
    )

    build_job_marker = "\n  build:\n"
    build_job_pos = content.index(build_job_marker)
    build_checkout = content.index(checkout_marker, build_job_pos)
    content = _insert_set_source(content, build_checkout, "build job")

    rs_job_marker = "\n  run_supervisor:\n"
    if rs_job_marker not in content:
        print("SKIP: run_supervisor job not found")
        return content
    rs_job_pos = content.index(rs_job_marker)
    rs_checkout = content.index(checkout_marker, rs_job_pos)
    return _insert_set_source(content, rs_checkout, "run_supervisor job")


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


def main() -> None:
    """Apply all fork-specific patches to builder.yml."""
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    filepath = root / ".github" / "workflows" / "builder.yml"

    if not filepath.exists():
        print(f"ERROR: {filepath} not found", file=sys.stderr)
        sys.exit(1)

    content = filepath.read_text(encoding="utf-8")
    content = patch_actions_helpers(content)
    content = patch_delete_push_trigger(content)
    content = patch_wheels_steps(content)
    content = patch_set_source_steps(content)
    content = patch_version_condition(content)
    content = patch_ghcr_addresses(content)
    filepath.write_text(content, encoding="utf-8")
    print(f"OK: patched {filepath}")


if __name__ == "__main__":
    main()
