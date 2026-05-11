#!/usr/bin/env bash
# Print the active install root for the claude-investment-skills toolkit.
#
# Resolves correctly for BOTH installation paths:
#   - Git clone:  ~/.claude/skills/             (manual install, the old way)
#   - Plugin:     ~/.claude/plugins/claude-investment-skills/   (via /plugin marketplace)
#
# Used by SKILL.md instructions whenever they invoke a Python script — lets
# the same command work in either mode without per-file conditional logic.
#
# Output: prints the resolved root directory to stdout, exits 0 on success.
# Exit 1 with stderr error if no install is detected.

set -e

# Probe order: git-clone path first (more common, older), then plugin path.
# A directory counts as a valid install if it contains the canonical anchor
# (review-investment-screenshot/scripts/, which all installs must have).
for candidate in \
  "$HOME/.claude/skills" \
  "$HOME/.claude/plugins/claude-investment-skills"; do
  if [[ -d "$candidate/review-investment-screenshot/scripts" ]]; then
    echo "$candidate"
    exit 0
  fi
done

echo "ERROR: claude-investment-skills install not found at any of:" >&2
echo "  ~/.claude/skills/             (git clone install)" >&2
echo "  ~/.claude/plugins/claude-investment-skills/   (plugin install)" >&2
echo "Re-run setup.sh or /plugin install claude-investment-skills." >&2
exit 1
