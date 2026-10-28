#!/bin/sh
# Apply one pinned kit version to a repo, then benchmark it against the other repo.
# Usage: apply-kit.sh <investment|dividend-growth> [vX.Y.Z] [--no-pr]
set -eu

KIT="$HOME/Projects/Personal/claude-kit"
BASE="$HOME/Projects/Personal"
BASE_BRANCH=develop

name=${1:?usage: apply-kit.sh <investment|dividend-growth> [vX.Y.Z] [--no-pr]}
version=${2:-v0.3.1}
pr_flag=${3:-}

case "$name" in
  investment) control=dividend-growth ;;
  dividend-growth) control=investment ;;
  *) echo "unknown repo: $name" >&2; exit 2 ;;
esac
repo="$BASE/$name"
kit() { uv run --project "$KIT" kit "$@"; }

# The tag must exist in the kit checkout; apply snapshots that tag, not the working tree.
git -C "$KIT" rev-parse -q --verify "refs/tags/$version" >/dev/null || { echo "no tag $version in $KIT" >&2; exit 1; }

# apply branches from the current HEAD and refuses a dirty tree, so start from an up-to-date develop.
[ -z "$(git -C "$repo" status --porcelain)" ] || { echo "$repo has uncommitted changes" >&2; exit 1; }
git -C "$repo" fetch origin
# bench reads history from origin/HEAD's branch, which a clone made before it was set lacks.
git -C "$repo" remote set-head origin --auto
git -C "$BASE/$control" remote set-head origin --auto
git -C "$repo" checkout "$BASE_BRANCH"
git -C "$repo" pull --ff-only origin "$BASE_BRANCH"

# A rerun after a failed apply needs the old branch gone (see the retry hint apply prints).
branch="chore/claude-kit-$version"
if git -C "$repo" rev-parse -q --verify "refs/heads/$branch" >/dev/null; then
  echo "branch $branch already exists in $repo; delete it or pick another version" >&2; exit 1
fi

kit status
# shellcheck disable=SC2086
kit apply "$repo" --version "$version" $pr_flag
kit bench "$repo" --control "$BASE/$control"
