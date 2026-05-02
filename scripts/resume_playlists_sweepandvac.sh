#!/bin/bash
# Resume the sweepandvac playlists step after YouTube quota reset.
# Designed to be invoked by launchd with a stripped environment.

set -u

PROJECT_ROOT="/Users/alexfairchild/Documents/Fairchild Heavy Industries/youtube-metadata-agent"
PYTHON="/usr/local/Caskroom/miniconda/base/bin/python"
LOG_DIR="$PROJECT_ROOT/clients/sweepandvac/output"
TIMESTAMP="$(date +%Y-%m-%d_%H%M%S)"
LOG_FILE="$LOG_DIR/playlists_resume_${TIMESTAMP}.log"

cd "$PROJECT_ROOT" || exit 1

mkdir -p "$LOG_DIR"

{
  echo "=== Resume sweepandvac playlists at $(date) ==="
  echo "Working dir: $(pwd)"
  echo "Python: $PYTHON"
  echo
} > "$LOG_FILE"

if [ -f "$PROJECT_ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$PROJECT_ROOT/.env"
  set +a
fi

DRY_RUN=false "$PYTHON" -m agent.playlists --client sweepandvac --approve >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

{
  echo
  echo "=== Exit code: $EXIT_CODE ==="
  echo "=== Finished at $(date) ==="
} >> "$LOG_FILE"

if [ $EXIT_CODE -eq 0 ]; then
  TITLE="Sweep & Vac playlists: success"
  MESSAGE="Resume completed cleanly. Log: $(basename "$LOG_FILE")"
else
  TITLE="Sweep & Vac playlists: FAILED (exit $EXIT_CODE)"
  MESSAGE="Check log: $(basename "$LOG_FILE")"
fi

osascript -e "display notification \"$MESSAGE\" with title \"$TITLE\" sound name \"Glass\""

# Self-disable: this is a one-shot job. Unload the plist so it doesn't fire again.
PLIST_LABEL="com.fairchild.youtube.resume-playlists"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
if [ -f "$PLIST_PATH" ]; then
  launchctl bootout "gui/$(id -u)/$PLIST_LABEL" 2>/dev/null || true
  rm -f "$PLIST_PATH"
fi

exit $EXIT_CODE
