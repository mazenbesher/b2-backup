# Sample `.env` file

```env
# sync
SRC_DIR='./src'
DST_BUCKET_NAME='bucket-name'

# b2 app key
APP_KEY_ID = '4a5b6c7d8e9f'
APP_KEY = '001b8e23c26ff6efb941e237deb182b9599a84bef7'
```

# Getting started

1. `python -m venv ./venv`
2. `source ./venv/bin/activate`
3. `pip install -r requirements.txt`
4. `vim .env`
5. `python main --dry-run --verbose`

# TODO

- [ ] unit tests from './playground'
