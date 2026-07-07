# Project Notes

## Current Goal

Set up a GitHub/Gitee-based workflow so the same project can be continued from different computers.

## Status

- Git is installed locally.
- GitHub is open in the browser.
- GitHub CLI (`gh`) is not installed on this computer.
- Command-line access to `https://github.com/zangxiaoxiao723/yammy723.git` timed out during initial testing.

## Decisions

- Use GitHub/Gitee plus project notes instead of relying on API chat history sync.
- Keep AI-facing context in `AGENTS.md`.
- Keep progress and decisions in this file.

## Next Steps

1. Confirm the GitHub repository URL.
2. Connect this local folder to the remote repository.
3. Commit and push the initial project context files.
4. On the second computer, clone the same repository and open it in Codex.

## Sync Workflow

Before starting work:

```powershell
git pull
```

After finishing work:

```powershell
git status
git add .
git commit -m "Update project"
git push
```
