# Publishing teloce-py

Use Python 3.11+ for the combined Flaxon/Teloce release workflow. From this repository, install the publishing tools:

```sh
python -m pip install --upgrade build twine
```

Before publishing, merge the intended changes, run the project's tests, choose a new unused version in `src/teloce/version.py`, and update the changelog. The script uses the current version; it does not bump versions, create Git tags, or run the test suite.

Build and validate without uploading:

```sh
python scripts/publish.py --build-only
```

Build, validate, and upload to TestPyPI:

```sh
python scripts/publish.py --repository testpypi
```

Publish to PyPI:

```sh
python scripts/publish.py
```

Twine can prompt for your API token, or use its keyring, `.pypirc`, or `TWINE_PASSWORD` configuration. Use `TWINE_USERNAME=__token__` for token authentication with older Twine versions. PyPI and TestPyPI use separate tokens. Keep credentials outside the repository. `--non-interactive` fails instead of prompting when authentication is unavailable.

Each invocation builds one wheel and one source distribution in a new `dist/publish-*` folder, then runs `twine check --strict`. Upload uses only those freshly checked files; older files in `dist` are ignored. The selected repository is passed as an explicit HTTPS URL. Failed builds/checks stop before upload, and artifacts are retained for inspection. Upload failures return a nonzero exit status; inspect PyPI before retrying if one artifact may already have uploaded.

These packages do not build native PyTSCheck or MinifyJS binaries. Their Python dependencies supply those binaries in their own distributions.

## Release order

Publish Teloce first. Then set Flaxon's `teloce-py` minimum dependency to that released version and publish Flaxon. This ensures new Flaxon installs receive the adapter required for automatic checks, project inheritance, and child-prop validation. A TestPyPI release does not satisfy a dependency downloaded from normal PyPI.

Update both `__version__` and `__version_info__` in Teloce's version file so the string and tuple agree. Standalone checking remains optional through `teloce-py[typecheck]`.
