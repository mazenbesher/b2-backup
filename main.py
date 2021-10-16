import re
import time
import sys
from pathlib import Path
from typing import Iterable, Union, Dict

import typer
from dotenv import dotenv_values
from gitignore_parser import parse_gitignore
from b2sdk.v2 import InMemoryAccountInfo
from b2sdk.v2 import B2Api
from b2sdk.v2 import ScanPoliciesManager
from b2sdk.v2 import parse_sync_folder
from b2sdk.v2 import SyncReport
from b2sdk.v2 import Synchronizer
from b2sdk.v2 import KeepOrDeleteMode, CompareVersionMode, NewerFileSyncMode


required_config_keys = [
    'SRC_DIR', 'DST_BUCKET_NAME',
    'APP_KEY_ID', 'APP_KEY',
]
app = typer.Typer()
ExcludedFiles = Iterable[Union[str, re.Pattern]]
global_ignores_regex = [
    re.compile(r) for r in Path('global-ignores-regex').read_text().split()
]


def check_config(config: Dict):
    # assert all keys are passed
    for key in required_config_keys:
        if not key in config:
            raise ValueError(f'{key} in .env is required')

    src_path: Path = Path(config['SRC_DIR'])
    if not src_path.exists():
        raise ValueError(f'src path {src_path} does not exist!')


def path_to_regex(path: Path) -> str:
    return path.as_posix().replace('/', '\/').replace('.', '\.')


def access(path: Path) -> bool:
    try:
        path.is_dir()
    except OSError:
        return False
    return True


def get_execluded_files(config: Dict, verbose: bool = False) -> ExcludedFiles:
    src_path: Path = Path(config['SRC_DIR'])

    def inner_iterator(curr_dir: Path = src_path):
        paths_in_curr_dir = list(curr_dir.iterdir())
        possible_gitignore_path = curr_dir / '.gitignore'

        has_gitignore = possible_gitignore_path in paths_in_curr_dir
        if has_gitignore:
            matches = parse_gitignore(possible_gitignore_path)

        for path in paths_in_curr_dir:
            if not access(path):
                print(f"Can't access {path}")
                continue
            global_match: bool = any(c.match(str(path)) is not None for c in global_ignores_regex)
            if global_match or (has_gitignore and matches(path)):
                if verbose:
                    print(f'excluding {path}')
                # remove first part of the path as it is the source
                path = path.relative_to(src_path)
                yield path_to_regex(path)
            elif path.is_dir():
                yield from inner_iterator(path)

    yield from inner_iterator()


def b2_sync(config: Dict, verbose: bool = False, dry_run: bool = False):
    info = InMemoryAccountInfo()
    b2_api = B2Api(info)
    b2_api.authorize_account(
        "production",
        config['APP_KEY_ID'],
        config['APP_KEY'],
    )

    policies_manager = ScanPoliciesManager(
        exclude_all_symlinks=True,
        exclude_file_regexes=get_execluded_files(config, verbose),
    )

    synchronizer = Synchronizer(
        max_workers=10,
        policies_manager=policies_manager,
        dry_run=dry_run,
        allow_empty_source=True,
        compare_version_mode=CompareVersionMode.MODTIME,
        compare_threshold=10,
        newer_file_mode=NewerFileSyncMode.REPLACE,
        keep_days_or_delete=KeepOrDeleteMode.DELETE,  # delete old folders
        keep_days=10,
    )

    src_path: Path = Path(config['SRC_DIR'])
    dst_bucket_name: str = config['DST_BUCKET_NAME']

    no_progress = True
    with SyncReport(sys.stdout, no_progress) as reporter:
        synchronizer.sync_folders(
            source_folder=parse_sync_folder(str(src_path), b2_api),
            dest_folder=parse_sync_folder(f'b2://{dst_bucket_name}', b2_api),
            now_millis=int(round(time.time() * 1000)),
            reporter=reporter,
        )


@app.command()
def show_excluded_files():
    config = dotenv_values(".env")
    get_execluded_files(config, verbose=True)


@app.command()
def sync(
    verbose: bool = typer.Option(False),
    dry_run: bool = typer.Option(False),
):
    config = dotenv_values(".env")
    check_config(config)
    # b2_sync(config, verbose, dry_run)
    print(list(get_execluded_files(config, verbose)))


@app.command()
def compute_backup_size(
    show_files: bool = typer.Option(False),
):
    size: int = 0
    config = dotenv_values(".env")
    src_path: Path = Path(config['SRC_DIR'])

    def inner_iterator(curr_dir: Path = src_path):
        nonlocal size
        paths_in_curr_dir = list(curr_dir.iterdir())
        possible_gitignore_path = curr_dir / '.gitignore'

        has_gitignore = possible_gitignore_path in paths_in_curr_dir
        if has_gitignore:
            matches = parse_gitignore(possible_gitignore_path)

        for path in paths_in_curr_dir:
            if not access(path):
                print(f"Can't access {path}")
                continue
            global_match: bool = any(c.match(str(path)) is not None for c in global_ignores_regex)
            if global_match or (has_gitignore and matches(path)):
                continue
            elif path.is_dir():
                inner_iterator(path)
            else:
                if show_files:
                    print(path)
                size += path.stat().st_size

    inner_iterator()
    print(f'{size:>12,} Bytes')
    print(f'{round(size / 1e3):>12,} KB')
    print(f'{round(size / 1e6):>12,} MB')
    print(f'{round(size / 1e9):>12,} GB')


if __name__ == "__main__":
    app()
