#!/bin/sh
# Open type:feedback issues in pending-resolution.
# Priority (critical, high, normal/unlabeled), then issue number.
# Prints JSON [{"number":N}, ...] for agent-orc issues.command and the gate.
set -eu

if ! command -v jq >/dev/null 2>&1; then
  echo "error: jq is required" >&2
  exit 1
fi

gh issue list --state open --label type:feedback --limit 100 --json number,labels \
  | jq '
      [.[]
       | select(any(.labels[].name; . == "status:pending-resolution"))]
      | map(. + {
          tier: ([.labels[].name]
            | if any(. == "priority:critical") then 0
              elif any(. == "priority:high") then 1
              else 2 end)
        })
      | sort_by(.tier, .number)
      | map({number})
    '
