Backup all files in a given directory to a backblaze b2 bucket while respeciting gitignore rules.

# `config.yaml`

## Required arguments

```yaml
# sync options
src_dir: './playground/src'
dst_bucket_name: "test-bucket"

# b2 app key
app_key_id: "4a5b6c7d8e9f"
app_key: "001b8e23c26ff6efb941e237deb182b9599a84bef7"
```

## Optional arguments

### Global patterns

```yaml
# global ignores
global_ignores:
  - ".*node_modules$"
  - ".*\\.git$"
  - ".*\\.ipynb_checkpoints$"
```

### Size limits

Exclude any ipython notebook larger than 5MB.

```yaml
size_limits:
  # size in MB
  ".*\\.ipynb$": ">=5"
```

## Tested defaults

```yaml
global_ignores:
  # caching files
  - ".*\\.data-\\d\\d\\d\\d-of-\\d\\d\\d\\d$"

  # caching folders
  - ".*node_modules$"
  - ".*\\.git$"
  - ".*\\.ipynb_checkpoints$"
  - ".*venv$"
  - ".*__pycache__$"

  # ml-models
  - ".*LibriSpeech$"
  - ".*\\.h5$"
  - ".*\\.pt$"

size_limits:
  # size in MB
  ".*\\.ipynb$": ">=5"
```

# Getting started

1. `python -m venv ./venv`
2. `source ./venv/bin/activate`
3. `pip install -r requirements.txt`
4. `vim config.yaml`
5. `python main.py sync --dry-run --verbose`

# Logging

1. `mkdir logs`
2. `make sync`

# TODO

- [ ] unit tests from './playground'
- [x] respecte nested rules
- [ ] upload full playground (ignore gitignore rules in that directory)
- [x] size caps
