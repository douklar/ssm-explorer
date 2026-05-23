<p align="center">
  <img src="assets/logo.png" alt="Douklar DevOps Tools Logo" width="300" />
</p>

<h1 align="center">SSM Explorer 🔍</h1>

<p align="center">
  <strong>Part of the Douklar DevOps Tools series.</strong>
</p>

<p align="center">
  <a href="https://github.com/douklar/ssm-explorer/actions/workflows/ci.yml"><img src="https://github.com/douklar/ssm-explorer/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License: MIT" /></a>
</p>

<p align="center">
  A <strong>professional</strong>, feature-rich CLI tool for searching, filtering, and inspecting AWS Systems Manager (SSM) Parameter Store parameters — with beautiful terminal output.
</p>

---

## Features

- 🔍 **Search** parameters by path prefix (recursive or flat)
- 🎯 **Filter** by environment variable name pattern (key or value)
- 📋 **List** all parameters under a path with `ENV_VAR → value` display
- 📤 **Export** parameters as `.env` file or JSON
- 🔐 **SecureString** decryption support
- 🗂️ **Multi-profile** AWS support via `--profile`
- 🌍 **Multi-region** support via `--region`
- 🖥️ **Beautiful Rich terminal tables** with pagination info
- 📦 **JSON output** mode for scripting and pipelines

### Fetch Speed

SSM Explorer defaults to `search.fetch_strategy = "auto"`:

- `batch` mode gets parameter names with `DescribeParameters` in pages of 50, then fetches values with parallel `GetParameters` batches of 10.
- If IAM denies the extra read APIs, `auto` falls back to the original `GetParametersByPath` flow.
- Client-side rate limits default to `max_get_tps = 20` and `max_describe_tps = 3` to stay under standard AWS Parameter Store quotas.

Use `search.fetch_strategy = "path"` in config to force the original single-API behavior.

---

## Installation

> **Requires Python 3.11+**

Poetry-first install. Run once from this repository:

```bash
cd SSM
poetry install
poetry run ssm-explorer install
```

Then run `ssm-explorer` from any directory:

```bash
ssm-explorer --help
ssm-explorer check --profile my_profile_aws --region eu-west-1
```

If `~/.local/bin` is not on your PATH, add it to your shell profile:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Uninstall the local wrapper:

```bash
ssm-explorer uninstall
```

This keeps the config file by default. To remove it too, run
`ssm-explorer uninstall --remove-config`.

`pipx install .` also works, but it is optional.

---

## Usage

```bash
ssm-explorer --help
ssm-explorer check
ssm-explorer config init
```

### Commands

#### `check` — Verify install, config, profile, region, and commands

```bash
# Uses config defaults
ssm-explorer check

# Or validate explicit profile/region
ssm-explorer check --profile my_profile_aws --region eu-west-1
```

`check` is offline by default. It validates local config, registered CLI commands,
local AWS profile names, and known SSM regions without calling AWS APIs.

#### `list` — List all parameters under a path

```bash
ssm-explorer list /my/path/to/var \
  --profile my_profile_aws \
  --region eu-west-1

# With decryption of SecureString values
ssm-explorer list /my/path/to/var \
  --profile my_profile_aws \
  --decrypt

# Output as JSON (for scripting)
ssm-explorer list /my/path/to/var \
  --profile my_profile_aws \
  --output json
```

#### `search` — Search/filter parameters by path or value pattern

```bash
# Search for parameters whose full path contains "DATABASE"
ssm-explorer search /my/path/to/var \
  --profile my_profile_aws \
  --filter-path DATABASE

# Search by value pattern
ssm-explorer search /my/path/to/var \
  --profile my_profile_aws \
  --filter-value "postgres://"

# Combine both
ssm-explorer search /my/path/to/var \
  --profile my_profile_aws \
  --filter-path DB \
  --filter-value "5432"
```

#### `get` — Get a single parameter value

```bash
ssm-explorer get /my/path/to/var/DATABASE_URL \
  --profile my_profile_aws \
  --decrypt
```

#### `diff` — Compare across paths, profiles, or regions

```bash
# Compare two different paths in the same account
ssm-explorer diff /app/dev /app/prod --profile my_profile_aws

# Compare same path across two AWS accounts (dev vs prod)
ssm-explorer diff /app/config \
  --profile-a my_dev_account \
  --profile-b my_prod_account

# Compare two AWS accounts in the same explicit region
ssm-explorer diff /app/config \
  --profile-a my_dev_account \
  --profile-b my_prod_account \
  --region eu-west-1

# Compare different paths across two AWS accounts
ssm-explorer diff /app/dev/config /app/prod/config \
  --profile-a my_dev_account \
  --profile-b my_prod_account

# Compare same account across regions
ssm-explorer diff /app/config \
  --profile-a default \
  --region-a us-east-1 \
  --region-b eu-west-1

# Compare two accounts and force explicit region per account
ssm-explorer diff /app/config \
  --profile-a stage_account \
  --region-a us-west-2 \
  --profile-b prod_account \
  --region-b eu-central-1

# Exclude identical values and show differences only
ssm-explorer diff /app/config \
  --profile-a stage_account \
  --profile-b prod_account \
  --region eu-west-1 \
  --exc-identicals

# Exclude parameters that exist only in Source B
ssm-explorer diff /app/config \
  --profile-a stage_account \
  --profile-b prod_account \
  --region eu-west-1 \
  --exc-missing-a

# Compare explicit source paths, then only diff parameters whose full path contains "browser"
ssm-explorer diff \
  --profile-a stage_account \
  --region-a us-west-2 \
  --path-a /app/config \
  --profile-b prod_account \
  --region-b eu-central-1 \
  --path-b /app/config \
  --filter-path browser
```

#### `export` — Export parameters to a .env or JSON file

```bash
# Export to .env file
ssm-explorer export /my/path/to/var \
  --profile my_profile_aws \
  --decrypt \
  --format env \
  --output-file .env

# Export to JSON
ssm-explorer export /my/path/to/var \
  --profile my_profile_aws \
  --format json \
  --output-file params.json
```

---

## Multi-Account & Multi-Region Support

SSM Explorer naturally supports querying multiple AWS accounts and regions.

### 1. Using CLI Flags (Ad-hoc)
You can manually specify the profile and region for any command:
```bash
ssm-explorer list /app/config --profile prod_account --region eu-west-1
```

### 2. Using Config Mapping (Recommended)
You can map specific AWS regions to specific AWS profiles in your `config.toml` file (located at `~/.config/ssm-explorer/config.toml` by default).

Once mapped, you only need to provide the `--profile` flag. The tool will automatically look up the correct region for that profile:

```toml
# config.toml
[aws]
profile = ""
region = ""

[aws.profiles.prod_account]
region = "eu-west-1"

[aws.profiles.dev_account]
region = "us-east-2"
```

With the above config, running this command will automatically fetch from `eu-west-1`:
```bash
ssm-explorer list /app/config --profile prod_account
```

This is incredibly useful for the `diff` command, where `--profile-a` and `--profile-b` will automatically inherit their mapped regions:
```bash
ssm-explorer diff /app/config --profile-a dev_account --profile-b prod_account
```

### 3. Auto-Resolve Profile From Environment Tags
If your runtime already has environment tags like `Environment=myapp-prod`, you can auto-resolve AWS profile without passing `--profile`:

```toml
[aws]
profile = ""
region = "eu-west-1"
profile_from_env_tags = ["Environment", "APP_ENV", "ENVIRONMENT"]

[aws.profile_from_env_value_map]
myapp-prod = "prod_account"
myapp-staging = "stage_account"
```

Resolution order:
1. `--profile` CLI flag
2. `aws.profile`
3. First non-empty env key from `aws.profile_from_env_tags` (optionally remapped via `aws.profile_from_env_value_map`)

---

## Terminal Output Example

```
┌─────────────────────────────────────────────────────────────────────┐
│              SSM Parameter Store — /my/path/to/var                  │
│                   Profile: my_profile_aws  •  Region: eu-west-1     │
└─────────────────────────────────────────────────────────────────────┘

 Parameter Store Results (5 parameters)

 ┌──────────────┬──────────────────────────────┬───────────────────┐
 │ ENV Variable │ Full Path                    │ Value             │
 ├──────────────┼──────────────────────────────┼───────────────────┤
 │ DATABASE_URL │ /my/path/to/var/DATABASE_URL │ postgres://db:... │
 │ REDIS_HOST   │ /my/path/to/var/REDIS_HOST   │ my-redis.cache... │
 │ API_KEY      │ /my/path/to/var/API_KEY      │ *** (encrypted)   │
 └──────────────┴──────────────────────────────┴───────────────────┘
```

---

## Project Structure

```
SSM/
├── pyproject.toml              # Poetry config & dependencies
├── poetry.lock                 # Locked dependency versions
├── README.md                   # This file
├── src/
│   └── ssm_explorer/
│       ├── __init__.py         # Package init & version
│       ├── main.py             # CLI entry point (Typer app)
│       ├── config.py           # Settings & configuration (Pydantic)
│       ├── commands/
│       │   ├── __init__.py
│       │   ├── list_cmd.py     # `list` command
│       │   ├── search_cmd.py   # `search` command
│       │   ├── get_cmd.py      # `get` command
│       │   └── export_cmd.py   # `export` command
│       ├── aws/
│       │   ├── __init__.py
│       │   └── ssm_client.py   # AWS SSM client wrapper
│       ├── models/
│       │   ├── __init__.py
│       │   └── parameter.py    # Pydantic data models
│       └── display/
│           ├── __init__.py
│           └── renderer.py     # Rich terminal rendering
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_ssm_client.py
    └── test_models.py
```

---

## Development

```bash
# Install with dev dependencies
poetry install

# Run linter
poetry run ruff check src/

# Run type checker
poetry run mypy src/

# Run tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=ssm_explorer
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, commit conventions, and PR workflow.

---

## License

MIT — see [LICENSE](LICENSE) for details.

---

*Built with ❤️ by [Douklar DevOps Tools](https://github.com/douklar)*
