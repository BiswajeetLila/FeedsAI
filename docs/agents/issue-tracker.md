# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues. Use the `gh` CLI for all issue-tracker operations.

## Prerequisites

- `gh` must be installed and authenticated.
- Run issue commands from a clone with a GitHub remote configured, or pass `--repo OWNER/REPO` explicitly.
- This repo should not use `.scratch/` as the canonical issue tracker.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`
- **Read an issue**: `gh issue view <number> --comments --json number,title,body,labels,comments,state`
- **List issues**: `gh issue list --state open --json number,title,body,labels`
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply or remove labels**: `gh issue edit <number> --add-label "..."` or `--remove-label "..."`
- **Close an issue**: `gh issue close <number> --comment "..."`

If a command needs a multi-line body, write the body to a temporary file or use the shell's native multi-line input support.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments --json number,title,body,labels,comments,state`.
