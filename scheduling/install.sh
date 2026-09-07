#!/bin/zsh
# Install (or refresh) the launchd agents for the daily signal runs.
# Idempotent: re-running replaces any previously loaded copies.
set -e
cd "$(dirname "$0")"
UID_N=$(id -u)
for name in com.pankaj.stock-signal-us com.pankaj.stock-signal-india; do
  cp "$name.plist" ~/Library/LaunchAgents/
  launchctl bootout "gui/$UID_N/$name" 2>/dev/null || true
  launchctl bootstrap "gui/$UID_N" ~/Library/LaunchAgents/"$name.plist"
  echo "loaded $name"
done
launchctl list | grep stock-signal
