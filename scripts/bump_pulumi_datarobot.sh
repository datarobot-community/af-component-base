#!/usr/bin/env bash
# Bump the pinned pulumi-datarobot version in the copier template and open a PR.
#
# Driven by the provider's own release, not by polling: pulumi-datarobot's
# release.yml dispatches a `pulumi-datarobot-released` event here once its SDK
# is published, and .github/workflows/bump-pulumi-datarobot.yaml runs this with
# the released version. Called without a version (a manual workflow_dispatch,
# or a local run) it falls back to resolving the newest published release
# itself.
#
# The provider is pinned in two places that must always agree:
#
#   template/infra/pyproject.toml.jinja   the Python SDK floor      ("pulumi-datarobot>=X.Y.Z")
#   template/infra/Taskfile.yaml.jinja    the pulumi plugin binary  (echo "vX.Y.Z")
#
# They drifted apart once already (PR #120 bumped the SDK floor and left the
# plugin behind), which is what this script exists to prevent. The download URL
# in Taskfile.yaml.jinja derives from the plugin version rather than repeating
# it, so there is no third pin -- this script asserts that derivation is still
# in place and refuses to run if someone re-hardcodes a version there.
#
# A release only counts as bumpable when it exists BOTH on PyPI (the SDK) and
# as a non-draft, non-prerelease GitHub release (the plugin binary). Bumping
# the SDK to a version whose plugin binary was never published would break
# every generated project, so agreement between the two is required -- and that
# holds for a version handed to us by the release dispatch too, which is why an
# explicit version is verified rather than trusted. The dispatch can arrive
# before PyPI's index catches up with its own publish API, so that check
# retries for a short while before giving up.
#
# This script never merges anything -- it only opens a PR for a human to
# review. It exits 0 (nothing to do) when already up to date, when a PR for the
# exact version transition is already open, and when PyPI or GitHub can't be
# reached (it retries on the next scheduled run). It exits 1 only when the two
# pins have drifted out of sync, when a file's shape is no longer what the
# script knows how to edit, or when a partial edit is detected -- all cases a
# human needs to look at rather than something this script should guess at.
#
# Usage:
#   scripts/bump_pulumi_datarobot.sh --check [<version>]
#       Determine the target version -- <version> if given (as the release
#       dispatch supplies it), otherwise the newest release published on both
#       PyPI and GitHub -- and, if a bump is warranted, apply the edits to the
#       working tree. Nothing is committed. Writes should_bump / current /
#       target / branch / pr_title to $GITHUB_OUTPUT when running in Actions,
#       and prints them either way.
#
#   scripts/bump_pulumi_datarobot.sh --open-pr <current> <target>
#       Commit the edits --check made, push a branch, and open the PR. Split
#       from --check so the workflow can run `task validate` against the edited
#       tree in between, and never opens a PR for a template that doesn't
#       validate.
#
# Requires: git, gh (authenticated, repo + PR write), jq, curl.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

PYPROJECT="template/infra/pyproject.toml.jinja"
TASKFILE="template/infra/Taskfile.yaml.jinja"

PROVIDER_REPO="datarobot-community/pulumi-datarobot"
PYPI_PACKAGE="pulumi-datarobot"

# How long to keep re-checking that a dispatched version is really installable.
# Six attempts at this spacing covers PyPI's index lag without stalling the job.
VERIFY_RETRY_DELAY="${VERIFY_RETRY_DELAY:-15}"

# Bare X.Y.Z (pyproject) and v-prefixed vX.Y.Z (pulumi plugin).
BARE_RE='[0-9]+\.[0-9]+\.[0-9]+'
SDK_LINE_RE='^[[:space:]]*"pulumi-datarobot>='"${BARE_RE}"'",$'
PLUGIN_LINE_RE='^[[:space:]]*echo "v'"${BARE_RE}"'"$'

# The derived download URL, as it appears in the .jinja source. Written this
# way so jinja renders it to a literal {{.PULUMI_DATAROBOT_PLUGIN_VERSION}}
# for Task to expand at run time.
DERIVED_URL_MARKER='releases/download/{{ "{{.PULUMI_DATAROBOT_PLUGIN_VERSION}}" }}'

# Emit a key=value pair to the step summary/outputs when running under Actions,
# and to stdout always, so a local run shows the same decision the workflow saw.
emit() {
  local key="$1" value="$2"
  echo "${key}=${value}"
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    echo "${key}=${value}" >>"$GITHUB_OUTPUT"
  fi
}

# Extract the single version matched by $line_re in $file, aborting loudly if
# there isn't exactly one matching line -- more or fewer means the file's shape
# changed in a way this script doesn't understand, so we refuse to guess.
read_single_pin() {
  local file="$1" line_re="$2" label="$3"
  local count versions distinct_count

  count="$(grep -cE "$line_re" "$file" || true)"
  if [ "$count" -ne 1 ]; then
    echo "ERROR: expected exactly 1 ${label} line in ${file}, found ${count}. The file's shape has changed -- update this script before it can safely bump it." >&2
    exit 1
  fi

  versions="$(grep -oE "$line_re" "$file" | grep -oE "$BARE_RE" | sort -u)"
  distinct_count="$(printf '%s\n' "$versions" | grep -c . || true)"
  if [ "$distinct_count" -ne 1 ]; then
    echo "ERROR: could not determine a single ${label} version in ${file}." >&2
    exit 1
  fi

  printf '%s' "$versions"
}

# True when $1 is a strictly newer version than $2. Guards against "bumping"
# backwards if someone has pinned ahead of the latest published release by hand.
version_gt() {
  [ "$1" != "$2" ] && [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | tail -n1)" = "$1" ]
}

# Newest version published on PyPI as a non-yanked release with files, and also
# cut as a non-draft, non-prerelease GitHub release. Prints nothing and returns
# non-zero if either source can't be read -- callers treat that as soft.
resolve_target_version() {
  local pypi_json pypi_versions gh_tags candidate

  if ! pypi_json="$(curl -fsS --retry 3 --retry-delay 2 --max-time 30 \
      "https://pypi.org/pypi/${PYPI_PACKAGE}/json")"; then
    return 1
  fi

  # A version with no files, or whose only files are yanked, is not installable.
  if ! pypi_versions="$(jq -r '
        .releases
        | to_entries[]
        | select(.value | length > 0)
        | select(any(.value[]; .yanked == false))
        | .key
      ' <<<"$pypi_json")"; then
    return 1
  fi

  if ! gh_tags="$(gh release list --repo "$PROVIDER_REPO" \
      --exclude-pre-releases --exclude-drafts --limit 50 \
      --json tagName --jq '.[].tagName')"; then
    return 1
  fi

  # Walk GitHub releases newest-first and take the first that PyPI also has.
  while read -r tag; do
    [ -n "$tag" ] || continue
    candidate="${tag#v}"
    if grep -qxF "$candidate" <<<"$pypi_versions"; then
      printf '%s' "$candidate"
      return 0
    fi
  done < <(printf '%s\n' "$gh_tags" | sort -Vr)

  return 1
}

# True when $1 is installable from PyPI (a non-yanked release with files) and
# cut as a non-draft, non-prerelease GitHub release. Retried, because the
# release dispatch can reach us before PyPI's index reflects its own publish.
version_available() {
  local version="$1" attempt pypi_json

  for attempt in 1 2 3 4 5 6; do
    if [ "$attempt" -gt 1 ]; then
      echo "  not visible yet, retrying in ${VERIFY_RETRY_DELAY}s (attempt ${attempt}/6)..." >&2
      sleep "$VERIFY_RETRY_DELAY"
    fi

    if ! pypi_json="$(curl -fsS --retry 3 --retry-delay 2 --max-time 30 \
        "https://pypi.org/pypi/${PYPI_PACKAGE}/${version}/json" 2>/dev/null)"; then
      continue
    fi

    # A version whose files are all yanked is published but not installable.
    if ! jq -e '.urls | length > 0 and any(.[]; .yanked == false)' >/dev/null 2>&1 <<<"$pypi_json"; then
      continue
    fi

    if ! gh release view "v${version}" --repo "$PROVIDER_REPO" \
        --json isDraft,isPrerelease \
        --jq 'select(.isDraft == false and .isPrerelease == false)' >/dev/null 2>&1; then
      continue
    fi

    return 0
  done

  return 1
}

do_check() {
  local requested="${1:-}"
  local sdk_version plugin_version current target

  # The derived URL is what makes two pins sufficient instead of three. If it
  # has been replaced with a hardcoded version, bumping the two pins we know
  # about would leave the URL stale -- exactly the bug this replaced.
  if ! grep -qF "$DERIVED_URL_MARKER" "$TASKFILE"; then
    echo "ERROR: ${TASKFILE} no longer derives the plugin download URL from PULUMI_DATAROBOT_PLUGIN_VERSION. Expected to find: ${DERIVED_URL_MARKER}" >&2
    echo "If the URL has been hardcoded again, this script would bump the version pins and leave the URL pointing at the old release. Fix the file or update this script." >&2
    exit 1
  fi

  sdk_version="$(read_single_pin "$PYPROJECT" "$SDK_LINE_RE" "pulumi-datarobot SDK floor")"
  plugin_version="$(read_single_pin "$TASKFILE" "$PLUGIN_LINE_RE" "pulumi plugin version")"

  # Drift check: both pins must already agree before we touch anything. If they
  # don't, someone bumped one by hand and we don't know which is authoritative.
  if [ "$sdk_version" != "$plugin_version" ]; then
    echo "ERROR: the pulumi-datarobot pins have drifted out of sync. Refusing to guess which is correct:" >&2
    echo "  ${PYPROJECT}: >=${sdk_version}" >&2
    echo "  ${TASKFILE}: v${plugin_version}" >&2
    exit 1
  fi

  current="$sdk_version"
  echo "Currently pinned pulumi-datarobot: ${current}"

  if [ -n "$requested" ]; then
    # A version handed over by the release dispatch. Verified rather than
    # trusted: the dispatch fires as soon as the SDK publish step finishes, and
    # a bump PR that lands before the package is installable would produce a
    # template nobody can resolve.
    if ! [[ "$requested" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
      echo "ERROR: requested version '${requested}' is not a bare X.Y.Z version." >&2
      exit 1
    fi

    echo "Requested version (from the release dispatch): ${requested}"
    echo "Confirming it is installable from PyPI and cut as a GitHub release..."
    if ! version_available "$requested"; then
      echo "WARNING: pulumi-datarobot ${requested} is not yet available on both PyPI and GitHub. Not opening a PR." >&2
      echo "Dispatch it again, or re-run this workflow once it is published." >&2
      emit should_bump false
      return 0
    fi
    echo "Confirmed ${requested} on both PyPI and GitHub."
    target="$requested"
  else
    # No version given (a manual run without an input, or a local invocation).
    # Soft failure: a transient PyPI/GitHub outage or an expired token looks the
    # same as "no releases found", so warn rather than failing the job.
    if ! target="$(resolve_target_version)" || [ -z "$target" ]; then
      echo "WARNING: could not determine a pulumi-datarobot release published on both PyPI and GitHub. Nothing to do." >&2
      emit should_bump false
      return 0
    fi
    echo "Latest release on both PyPI and GitHub: ${target}"
  fi

  if [ "$target" = "$current" ]; then
    echo "pulumi-datarobot is already up to date (${current}). Nothing to do."
    emit should_bump false
    return 0
  fi

  if ! version_gt "$target" "$current"; then
    echo "The pinned version (${current}) is newer than the latest published release (${target}). Leaving it alone."
    emit should_bump false
    return 0
  fi

  local branch="auto/bump-pulumi-datarobot-${current}-to-${target}"
  local pr_title="chore: bump pulumi-datarobot from ${current} to ${target}"

  # De-dup on branch names, not on a title/body search. `gh pr list --search` is
  # a fuzzy full-text query: searching for the version strings also matches any
  # unrelated open PR that merely mentions them (it matched the PR that
  # introduced this script), which would silently suppress real bumps.
  #
  # Two branch shapes count as "already proposed": this script's own, and
  # Dependabot's (dependabot/pip/.../pulumi-datarobot-<version>), so a daily
  # Dependabot backstop and this release-triggered path can coexist without
  # both opening a PR for the same version.
  # Compared literally via endswith, not with a regex: the version contains
  # dots, and a regex would need escaping that jq string literals make
  # error-prone. A false positive here silently skips a real bump.
  local existing
  existing="$(gh pr list --state open --json number,headRefName 2>/dev/null \
    | jq -r --arg branch "$branch" --arg suffix "pulumi-datarobot-${target}" \
        '[.[] | select(.headRefName == $branch or (.headRefName | endswith($suffix)))] | .[0].number // empty' \
    2>/dev/null || true)"
  if [ -n "$existing" ]; then
    echo "An open PR already proposes pulumi-datarobot ${target} (#${existing}). Nothing to do."
    emit should_bump false
    return 0
  fi

  # No open PR, but the branch still exists on the remote: someone closed that
  # PR deliberately. Recreating it would reopen a decision a human already made,
  # and force-pushing over their branch is worse. Skip loudly instead.
  if git ls-remote --exit-code --heads origin "$branch" >/dev/null 2>&1; then
    echo "Branch ${branch} already exists on origin but has no open PR -- its PR was probably closed on purpose. Skipping." >&2
    echo "Delete the remote branch if this bump should be proposed again." >&2
    emit should_bump false
    return 0
  fi

  apply_bump "$current" "$target"

  emit should_bump true
  emit current "$current"
  emit target "$target"
  emit branch "$branch"
  emit pr_title "$pr_title"
}

# Edit precisely: match the exact line shape in each file rather than doing a
# blind find-and-replace that could touch an unrelated occurrence of the same
# version string.
apply_bump() {
  local current="$1" target="$2" escaped f
  escaped="$(printf '%s' "$current" | sed -E 's/\./\\./g')"

  sed -E "s/^([[:space:]]*)\"pulumi-datarobot>=${escaped}\",\$/\\1\"pulumi-datarobot>=${target}\",/" \
    "$PYPROJECT" >"${PYPROJECT}.bump_tmp"
  mv "${PYPROJECT}.bump_tmp" "$PYPROJECT"

  sed -E "s/^([[:space:]]*)echo \"v${escaped}\"\$/\\1echo \"v${target}\"/" \
    "$TASKFILE" >"${TASKFILE}.bump_tmp"
  mv "${TASKFILE}.bump_tmp" "$TASKFILE"

  # Confirm the old version is actually gone from both files before anything is
  # committed -- a partial bump (one sed pattern silently failing to match) is
  # worse than no bump at all.
  local failed=0
  for f in "$PYPROJECT" "$TASKFILE"; do
    if grep -qF "$current" "$f"; then
      echo "ERROR: ${current} is still present in ${f} after editing." >&2
      failed=1
    fi
  done

  if [ "$failed" -ne 0 ]; then
    echo "Reverting partial edit and aborting." >&2
    git checkout -- "$PYPROJECT" "$TASKFILE"
    exit 1
  fi

  echo "Applied bump ${current} -> ${target} to ${PYPROJECT} and ${TASKFILE}."
}

do_open_pr() {
  local current="$1" target="$2"
  local branch="auto/bump-pulumi-datarobot-${current}-to-${target}"
  local pr_title="chore: bump pulumi-datarobot from ${current} to ${target}"

  if git diff --quiet -- "$PYPROJECT" "$TASKFILE"; then
    echo "ERROR: no changes staged in ${PYPROJECT} or ${TASKFILE}. Run --check first." >&2
    exit 1
  fi

  git checkout -b "$branch"
  git add "$PYPROJECT" "$TASKFILE"
  git commit -m "$pr_title"
  git push -u origin "$branch"

  local body_file
  body_file="$(mktemp)"
  # shellcheck disable=SC2064  # expand body_file now, not at trap time
  trap "rm -f '$body_file'" EXIT

  cat >"$body_file" <<BODY_EOF
Automated bump of the [pulumi-datarobot](https://github.com/${PROVIDER_REPO}) provider (\`${current}\` -> \`${target}\`), picked up from the latest release published on both PyPI and GitHub.

## Files changed

- \`${PYPROJECT}\` -- the Python SDK floor (\`pulumi-datarobot>=${target}\`)
- \`${TASKFILE}\` -- the pulumi plugin binary version (\`v${target}\`)

These two must always agree. The plugin download URL derives from the plugin version, so it follows automatically and is not edited here.

## Verification

\`task validate\` passed against these edits before this PR was opened -- see the workflow run that created it. Because the run opens this PR with \`GITHUB_TOKEN\`, GitHub will not trigger \`validate-template.yaml\` on it, so that run's log is where the validation evidence lives rather than a check on this PR.

Worth a human eye on the release notes: \`pulumi-datarobot\` is a \`0.x\` provider, so a minor bump can carry breaking resource changes even though this looks routine.

This automation never auto-merges.
BODY_EOF

  gh pr create --base "$(gh repo view --json defaultBranchRef --jq '.defaultBranchRef.name')" \
    --title "$pr_title" --body-file "$body_file"
}

case "${1:-}" in
  --check)
    if [ "$#" -gt 2 ]; then
      echo "Usage: $0 --check [<version>]" >&2
      exit 1
    fi
    do_check "${2:-}"
    ;;
  --open-pr)
    if [ "$#" -ne 3 ]; then
      echo "Usage: $0 --open-pr <current> <target>" >&2
      exit 1
    fi
    do_open_pr "$2" "$3"
    ;;
  *)
    echo "Usage: $0 --check [<version>] | --open-pr <current> <target>" >&2
    exit 1
    ;;
esac
