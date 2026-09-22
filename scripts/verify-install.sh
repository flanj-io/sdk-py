#!/usr/bin/env bash
#
# Install flanj into a clean virtualenv and assert the zero-code entry's startup
# notice names the given version and OTLP endpoint. This is the check that matters:
# every check before it (tag match, twine, wheel contents) can pass on a wheel that
# still fails to import for a stranger.
#
# Used twice by .github/workflows/release.yml, with the same assertion against two
# different sources: once against the wheel this run just built (before upload,
# where a red here blocks the publish), once against the real PyPI package (after
# upload, anonymously — nothing but the public index).
#
# Usage: verify-install.sh <python-version> <expected-version> <source>
#   <source> is a path to a built wheel, or the literal word "pypi" to install
#   "flanj==<expected-version>" from PyPI instead.
#
# Requires FLANJ_OTLP_ENDPOINT in the environment (the value the notice must name)
# and `uv` on PATH.
set -euo pipefail

PYVER="${1:?usage: verify-install.sh <python-version> <expected-version> <source>}"
WANT_VERSION="${2:?usage: verify-install.sh <python-version> <expected-version> <source>}"
SOURCE="${3:?usage: verify-install.sh <python-version> <expected-version> <source>}"
: "${FLANJ_OTLP_ENDPOINT:?FLANJ_OTLP_ENDPOINT must be set in the environment}"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

uv venv --python "$PYVER" "$WORK/venv" >/dev/null

if [ "$SOURCE" = "pypi" ]; then
  echo "installing flanj==$WANT_VERSION from PyPI, anonymously"
  # The index lags the upload: seconds after a publish the simple index can
  # still answer without the new release ("no version of flanj==X"), and the
  # first real release verification failed exactly there while the file was
  # already served. Retry with a fresh index read; nothing else is retried.
  attempt=1
  until uv pip install --python "$WORK/venv/bin/python" -q --refresh "flanj==$WANT_VERSION"; do
    if [ "$attempt" -ge 10 ]; then
      echo "flanj==$WANT_VERSION is still not resolvable from PyPI after $attempt attempts" >&2
      exit 1
    fi
    echo "  not on the index yet (attempt $attempt) — waiting 30s"
    attempt=$((attempt + 1))
    sleep 30
  done
else
  [ -f "$SOURCE" ] || { echo "::error::no such wheel: $SOURCE"; exit 1; }
  echo "installing $(basename "$SOURCE")"
  uv pip install --python "$WORK/venv/bin/python" -q "$SOURCE"
fi

cat > "$WORK/probe.py" <<'PY'
import flanj.register  # noqa: F401 - the zero-code entry, exactly as a user's first line
PY

# Run from outside the repo (and outside dist/): a stray src/ on sys.path, or the
# wheel's own directory, would mask exactly the packaging bug this exists to catch.
cd "$WORK"
"$WORK/venv/bin/python" "$WORK/probe.py" 2> "$WORK/stderr.txt" || {
  cat "$WORK/stderr.txt" >&2
  echo "::error::'import flanj.register' failed on Python $PYVER"
  exit 1
}
cat "$WORK/stderr.txt"

grep -q "flanj $WANT_VERSION " "$WORK/stderr.txt" || {
  echo "::error::startup notice does not name version $WANT_VERSION"
  exit 1
}
grep -qF "$FLANJ_OTLP_ENDPOINT" "$WORK/stderr.txt" || {
  echo "::error::startup notice does not name endpoint $FLANJ_OTLP_ENDPOINT"
  exit 1
}
echo "Python $PYVER ($SOURCE): startup notice names flanj $WANT_VERSION -> $FLANJ_OTLP_ENDPOINT"
