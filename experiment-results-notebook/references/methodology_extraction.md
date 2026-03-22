# Methodology Extraction

Use these evidence sources in descending order of confidence:

1. Structured config changes in `yaml`, `yml`, `json`, and `toml`
2. Supporting repo code outside the experiment output folders:
   - preprocessing scripts
   - data pipeline code
   - split/windowing utilities
   - model factory or trainer code
   - reporting scripts
3. Explicit metric files and experiment manifests
4. Git commit messages and changed file paths
5. GitHub PR title, description, and changed files
6. User-written notes already present in the notebook

When writing methodology:

- Prefer concrete operational descriptions over vague phrases like "improved the setup".
- Do not stop at parameter lists. Explain the pipeline step the parameter controls and why it matters.
- Mention the mechanism of change when recoverable from the code or config.
- Separate confirmed facts from inference. Use language like `This suggests` when the code does not prove the intent.
- Do not repeat every file. Group related edits into 2-4 methodological themes.
- Always try to answer:
  - What raw or processed data artifact is being used?
  - What preprocessing or filtering happens before training?
  - How are splits, windows, chunks, or samples created?
  - What are the model inputs and prediction target?
  - What evaluation or post-eval selection procedure determines the reported result?

Useful signals:

- New or modified config keys
- Added or removed experiment directories
- New training/evaluation scripts
- Changed dataset paths or augmentation options
- New checkpoints, predictions, plots, or tables
- Module docstrings and function names such as `preprocess`, `clean`, `merge`, `split`, `window`, `evaluate`, or `report`
