# CHANGELOG

<!-- version list -->

## v1.0.2 (2026-05-23)

### Bug Fixes

- Bypass mypy typer_rich_utils assignment check without comments via __dict__
  ([`94efab3`](https://github.com/douklar/ssm-explorer/commit/94efab3b093b19a00851318e3b30777aca5b4bf0))

### Chores

- **ci**: Pin action versions by SHA, enable Node 24, and reconfigure dependabot settings
  ([`d8b8ea1`](https://github.com/douklar/ssm-explorer/commit/d8b8ea134a736dd22de31d18b703143126d2e692))

### Code Style

- Apply ruff format to all source files
  ([`7af5cdb`](https://github.com/douklar/ssm-explorer/commit/7af5cdbfaab456d17c2c555d15bc33b16bde2b16))

- Apply ruff format; fix lockfile sync to push-only
  ([`8b85534`](https://github.com/douklar/ssm-explorer/commit/8b85534432e4492f97a227bf0351ae254b5d08cd))

### Refactoring

- Add type annotations and use setattr for typer_rich_utils configuration updates
  ([`ec22e63`](https://github.com/douklar/ssm-explorer/commit/ec22e63e09f55208691df2f8c87ece52d0fb10f8))


## v1.0.1 (2026-05-23)

### Bug Fixes

- **lint**: Add 'from None' to typer.Exit raises to satisfy ruff B904
  ([`71c3a38`](https://github.com/douklar/ssm-explorer/commit/71c3a38192dba360c7554fe337b0b9b51c92b553))

### Chores

- Auto-sync poetry.lock [skip ci]
  ([`38436da`](https://github.com/douklar/ssm-explorer/commit/38436da9d8fab2fa07765f94308bce78b984f747))

- Configure dependabot updates [skip ci]
  ([`550d1f1`](https://github.com/douklar/ssm-explorer/commit/550d1f191d87c55e969e4f4a7af3350fc4c854e0))

- Group dependabot updates to prevent too many parallel actions
  ([`7a6fde8`](https://github.com/douklar/ssm-explorer/commit/7a6fde87daf24d8686ac85c7fc9bfc92355cfd1f))

### Continuous Integration

- Add automated lockfile sync step
  ([`f8f6576`](https://github.com/douklar/ssm-explorer/commit/f8f65760dbc379789869b3bedf5aad575d894a9e))

- Fix poetry caching and python environment binding
  ([`1a5c26a`](https://github.com/douklar/ssm-explorer/commit/1a5c26a2a1076345f660d9a9261d9299dc245fba))

- Fix poetry lock command and limit sync step to python 3.12
  ([`bc5d4e2`](https://github.com/douklar/ssm-explorer/commit/bc5d4e2bfb62eb8d2734b92e59f2c827b5cede8a))

- Optimize matrix build by running static analysis on python 3.12 only
  ([`d33f163`](https://github.com/douklar/ssm-explorer/commit/d33f163f7b867a8d3764af1f02aba258871cd793))

### Documentation

- Add security policy
  ([`2d35ec1`](https://github.com/douklar/ssm-explorer/commit/2d35ec1eda22180f43642f3d384ea8a6021a6df0))


## v1.0.0 (2026-05-23)

- Initial Release
