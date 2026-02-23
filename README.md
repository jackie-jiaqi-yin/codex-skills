# codex-skills

Custom Codex skills by [jackie-jiaqi-yin](https://github.com/jackie-jiaqi-yin).

## Available skills

- `arxiv-latest-summary`: Generate readable summaries of the latest arXiv papers and export HTML/PDF reports.

## Install (recommended: Codex `skill-installer`)

Run this from any terminal:

```bash
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
python "$CODEX_HOME/skills/.system/skill-installer/scripts/install-skill-from-github.py" \
  --repo jackie-jiaqi-yin/codex-skills \
  --path arxiv-latest-summary
```

If you add more skills later, install multiple in one command:

```bash
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
python "$CODEX_HOME/skills/.system/skill-installer/scripts/install-skill-from-github.py" \
  --repo jackie-jiaqi-yin/codex-skills \
  --path arxiv-latest-summary \
  --path <another-skill-folder>
```

Restart Codex after install so new skills are loaded.

## Install manually (no installer script)

```bash
git clone https://github.com/jackie-jiaqi-yin/codex-skills.git
cd codex-skills

CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
mkdir -p "$CODEX_HOME/skills"
cp -R arxiv-latest-summary "$CODEX_HOME/skills/"
```

Restart Codex after copying files.

## Verify installation

```bash
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
ls "$CODEX_HOME/skills"
```

You should see `arxiv-latest-summary` in the output.

## Next step in Codex (after install)

After restarting Codex, ask for a scoped run first, then optionally request automation.

Example:

```text
Use $arxiv-latest-summary for "health AI agents". Window: 7 days. Max papers: 50. Style: executive brief.
After confirming scope, turn this into a weekly Codex automation and provide the complete automation prompt with no placeholders.
```

## Update or reinstall a skill

The installer stops if the destination already exists. Remove the old copy first, then reinstall:

```bash
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
rm -rf "$CODEX_HOME/skills/arxiv-latest-summary"
python "$CODEX_HOME/skills/.system/skill-installer/scripts/install-skill-from-github.py" \
  --repo jackie-jiaqi-yin/codex-skills \
  --path arxiv-latest-summary
```

## Uninstall

```bash
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
rm -rf "$CODEX_HOME/skills/arxiv-latest-summary"
```

## Notes

- This repository stores installable skill folders (each contains a `SKILL.md`).
- For `arxiv-latest-summary`, running its Python workflow scripts may require extra Python packages (for example `requests`, `markdown2`, and one PDF backend like `weasyprint` or `reportlab`).
