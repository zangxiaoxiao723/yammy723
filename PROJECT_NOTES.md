# Project Notes

## Current Goal

Keep cross-computer project context synchronized, currently including the HPDI low-temperature pump sound analysis and the product-level mechanical verification restart.

## Status

- Git is installed locally.
- GitHub is open in the browser.
- GitHub CLI (`gh`) is not installed on this computer.
- Repository remote is `https://github.com/zangxiaoxiao723/yammy723.git`.
- HPDI project handoff files are stored under `projects/hpdi-pump-noise-analysis-202607/`.
- Product verification context is stored in `projects/hpdi-pump-noise-analysis-202607/PRODUCT_VERIFICATION_HANDOFF.md`.

## Decisions

- Use GitHub/Gitee plus project notes instead of relying on API chat history sync.
- Keep AI-facing context in `AGENTS.md`.
- Keep progress and decisions in this file.
- For HPDI analysis, keep reports, plots, CSV outputs, scripts, and handoff notes in Git.
- Do not commit raw HPDI videos/WAV by default because the files are large and may contain sensitive company test data.

## Next Steps

1. Pull this repository on the second computer.
2. Open `projects/hpdi-pump-noise-analysis-202607/README.md`.
3. Open `projects/hpdi-pump-noise-analysis-202607/CODEX_HANDOFF.md` before asking Codex to continue.
4. For new HPDI test data, rerun the same loudness method and compare P90/P95 against the baseline CSV.
5. For product verification, continue with the motion/valve-state questions in `PRODUCT_VERIFICATION_HANDOFF.md` before resuming calculations.

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
