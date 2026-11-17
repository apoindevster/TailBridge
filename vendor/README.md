# Display overlay

The SunFounder overlay is not redistributed in the repository or build artifacts.
Its redistribution license could not be established at the pinned source revision.
The main installer downloads it directly from the vendor's public repository and
checks the pinned SHA-256 before changing display configuration. See
`packaging/display-source.json` and `docs/THIRD-PARTY.md` for provenance.

For a prepared offline copy, run `python3 scripts/fetch_display.py` from an
extracted bundle while online. The resulting `mhs35ips.dtbo` is ignored by Git.
OS package installation can still need network access.
