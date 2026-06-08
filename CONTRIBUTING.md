# Contributing to FH6 Overlay

Thank you for your interest in contributing. All types of contributions are welcome — bug fixes, new features, documentation improvements, and translations.

## License and Ownership

This project is released under a **Custom Source-Available License**. By submitting a contribution (pull request, patch, or otherwise), you agree that:

- Your contribution is your own original work.
- You grant SkoiZz full, irrevocable rights to use, modify, and distribute your contribution as part of this project under any license, present or future.
- You may **not** publish, distribute, or sublicense your contribution separately or as part of a fork without the prior written permission of the copyright holder.

If you are not comfortable with these terms, please do not submit a contribution.

## How to Contribute

### Reporting Bugs

Open an issue with:
- A clear title and description of the problem.
- Steps to reproduce it.
- What you expected vs. what actually happened.
- Your OS version, controller type, and whether you're running the exe or from source.
- The contents of `fh6overlay.log` (next to the exe) if a crash or error occurred.

### Suggesting Features

Open an issue tagged `enhancement`. Describe what you want, why it would be useful, and any ideas on how it could work. Discuss before building — large PRs with no prior discussion may not be accepted.

### Submitting a Pull Request

1. **Fork** the repository and create a branch from `main`.
2. Keep changes focused — one bug fix or feature per PR.
3. Test your changes before submitting. If you add new behaviour, add or update tests in the test suite.
4. Write clear commit messages describing *why* the change was made, not just what.
5. Open the PR against the `main` branch.
6. In your PR description, include:
   - What the change does.
   - How you tested it.
   - The sign-off line below.

### Contributor Sign-Off

Every pull request must include the following line in the PR description:

```
I have read and agree to the contribution terms of this project's license. I grant SkoiZz full rights to this contribution.
```

PRs without this line will not be reviewed.

## Code Style

- Python 3.13+. Follow existing code style — no new dependencies without discussion.
- UI is built with **PyQt6** and **Qt Quick** (`QQuickWindow`, `QQuickPaintedItem`). Keep widget logic in the relevant module (`overlay.py`, `settings_panel.py`, `setup_wizard.py`). Visual element logic belongs in the `elements/` package.
- New visual styles for an element go in the corresponding `elements/*.py` file. Add the style key to the appropriate catalogue in `config.py` (`RPM_STYLES`, `BRAKE_STYLES`, etc.) and a human-readable label to `STYLE_LABELS`.
- Config reads and writes go through `config.py`. Do not access `config.ini` directly from other modules.
- All paint code runs on the Qt rendering thread — keep it fast and do not allocate heavy objects inside `paint()`.

## Build

To build the exe locally:

```
pip install pyinstaller
python -m PyInstaller FH6Overlay.spec
```

The output will be in `dist/`.

## Running Tests

```
pytest tests/
```

## Questions

Open an issue or start a discussion on GitHub.
