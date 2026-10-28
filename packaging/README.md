# Packaging

- `build-release.ps1`: clean source zip + SHA-256 (see docs/SHARING_AND_DISTRIBUTION.md §2).
  Dry run by default; refuses to include databases, configs, logs, backups, models or environments.
- A frozen one-folder app (PyInstaller or Nuitka) and an installer (Inno Setup/MSIX) are **P2**
  and not yet provided. Expected size is 250–400 MB because of PySide6. Code signing is needed to
  avoid SmartScreen warnings.
