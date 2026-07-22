# AGENTS.md

## Project Purpose

Keep the user's project files and AI collaboration notes synchronized across multiple computers through GitHub or Gitee.

The most active technical project is now:

- `projects/hpdi-pump-noise-analysis-202607/`

This project compares HPDI low-temperature pump thump loudness between Dongde competitor and FuRui self-developed pump, and tracks mechanical/hydraulic hypotheses after oil-cylinder changes.

## Working Rules for AI Assistants

- Read this file and `PROJECT_NOTES.md` before making changes.
- For HPDI work, also read `projects/hpdi-pump-noise-analysis-202607/README.md` and `projects/hpdi-pump-noise-analysis-202607/CODEX_HANDOFF.md`.
- Preserve user-created files and unrelated edits.
- Prefer small, clear commits with descriptive messages.
- Keep project context, decisions, and next steps updated in `PROJECT_NOTES.md`.
- Use Git for synchronization instead of relying on local chat history.
- For HPDI sound analysis, prioritize P90/P95 relative thump loudness over event counting.

## Environment Notes

- Primary OS observed: Windows.
- Shell observed: PowerShell.
- Current sync target: GitHub repository, likely `zangxiaoxiao723/yammy723`.

## Useful Commands

```powershell
git status
git pull
git add .
git commit -m "Describe the change"
git push
```
