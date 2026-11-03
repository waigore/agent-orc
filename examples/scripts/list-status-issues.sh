#!/bin/sh
# List open issues with the given status label, ordered for parallel claims:
# priority (critical, high, then normal/unlabeled), then type
# (defect, task, epic), then earlier Wave N milestone (no Wave N last),
# then issue number. Discovering agents still judge; see workflow-dispatch.md.
# Prints JSON [{"number":N}, ...] for agent-orc issues.command.
# Usage: list-status-issues.sh status:pending-review
set -eu

STATUS_LABEL=${1:?usage: list-status-issues.sh status:LABEL}

if ! command -v jq >/dev/null 2>&1; then
  echo "error: jq is required" >&2
  exit 1
fi

gh issue list --state open --label "$STATUS_LABEL" --limit 100 --json number,labels,milestone \
  | jq '
      def tier:
        ([.labels[].name]
         | if any(. == "priority:critical") then 0
           elif any(. == "priority:high") then 1
           else 2 end);
      def kind:
        ([.labels[].name]
         | if any(. == "type:defect") then 0
           elif any(. == "type:task") then 1
           elif any(. == "type:epic") then 2
           else 3 end);
      def wave:
        (.milestone.title // "") as $t
        | if ($t | test("^Wave [0-9]+")) then
            ($t | capture("^Wave (?<n>[0-9]+)") | .n | tonumber)
          else 1000000 end;
      sort_by(tier, kind, wave, .number) | map({number})
    '
