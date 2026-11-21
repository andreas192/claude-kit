#!/bin/sh
# Apply one pinned kit version to a repo from a temporary worktree, then benchmark it against a control repo.
# Usage: apply-kit.sh <investment|dividend-growth|claude-kit> [vX.Y.Z] [--no-pr]
#
# The repo's own checkout is never switched, stashed or committed to: the apply runs in a detached worktree of
# origin/<default branch> at ~/.claude/kit/apply/<repo>, which is removed on exit, pass or fail. Only
# `kit bench` writes the checkout, its gitignored .claude/kit-bench/, as before.
set -eu

KIT="$HOME/Projects/Personal/claude-kit"
BASE="${APPLY_KIT_BASE:-$HOME/Projects/Personal}"   # override only in tests
KIT_HOME="$HOME/.claude/kit"
USAGE="usage: apply-kit.sh <investment|dividend-growth|claude-kit> [vX.Y.Z] [--no-pr]"

name=${1:?$USAGE}
version=${2:-v0.5.2}
pr_flag=${3:-}

case "$name" in
  investment) control=dividend-growth ;;
  dividend-growth) control=investment ;;
  claude-kit) control=investment ;;
  *) echo "unknown repo: $name" >&2; echo "$USAGE" >&2; exit 2 ;;
esac
repo="$BASE/$name"
worktree="$KIT_HOME/apply/$name"
branch="chore/claude-kit-$version"
kit() { uv run --project "$KIT" kit "$@"; }

# The tag must exist in the kit checkout; apply snapshots that tag, not the working tree.
git -C "$KIT" rev-parse -q --verify "refs/tags/$version" >/dev/null || { echo "no tag $version in $KIT" >&2; exit 1; }

git -C "$repo" fetch origin
# bench reads history from origin/HEAD's branch, which a clone made before it was set lacks.
git -C "$repo" remote set-head origin --auto >/dev/null
git -C "$BASE/$control" remote set-head origin --auto >/dev/null
base_branch=$(git -C "$repo" rev-parse --abbrev-ref origin/HEAD | sed 's#^origin/##')

# A rerun after a failed apply needs the old branch gone, here and on origin.
if git -C "$repo" rev-parse -q --verify "refs/heads/$branch" >/dev/null; then
  echo "branch $branch already exists in $repo; delete it (git -C $repo branch -D $branch) or pick another version" >&2; exit 1
fi
if git -C "$repo" ls-remote --exit-code --heads origin "$branch" >/dev/null 2>&1; then
  echo "branch $branch already exists on origin of $repo; delete it or pick another version" >&2; exit 1
fi
if [ -e "$worktree" ]; then
  echo "$worktree is left from an earlier run; remove it with: git -C $repo worktree remove --force $worktree (or delete the folder if git does not list it in git -C $repo worktree list)" >&2; exit 1
fi

# The worktree directory is named after the repo, so apply's loop label and PR notes name the right agent.
mkdir -p "$KIT_HOME/apply"
git -C "$repo" worktree add --detach "$worktree" "origin/$base_branch"
cleanup() {
  status=$?
  git -C "$repo" worktree remove --force "$worktree" || true
  if [ "$status" -ne 0 ] && git -C "$repo" rev-parse -q --verify "refs/heads/$branch" >/dev/null; then
    echo "apply failed; to retry: git -C $repo branch -D $branch" >&2
  fi
}
trap cleanup EXIT

echo "applying $version to $name from $worktree (origin/$base_branch); $repo stays on $(git -C "$repo" branch --show-current)"
kit status
# shellcheck disable=SC2086
kit apply "$worktree" --version "$version" $pr_flag
kit bench "$repo" --control "$BASE/$control"
