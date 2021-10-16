import re
import time
import sys
from pathlib import Path
from typing import Iterable, Union, Dict

from dotenv import dotenv_values
from gitignore_parser import parse_gitignore
import typer
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
ExcludedFiles = Iterable[Union[str, re.Pattern]]
app = typer.Typer()


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


def get_execluded_files(config: Dict, verbose: bool = False) -> ExcludedFiles:
    src_path: Path = Path(config['SRC_DIR'])
    excluded_files: ExcludedFiles = []

    def inner_iterator(curr_dir: Path = src_path):
        paths_in_curr_dir = list(curr_dir.iterdir())
        possible_gitignore_path = curr_dir / '.gitignore'

        has_gitignore = possible_gitignore_path in paths_in_curr_dir
        if has_gitignore:
            # if verbose: print(f'{curr_dir} has a .gitignore')
            matches = parse_gitignore(possible_gitignore_path)

        for path in paths_in_curr_dir:
            if has_gitignore and matches(path):
                if verbose:
                    print(f'excluding {path}')
                # remove first part of the path as it is the source
                path = path.relative_to(src_path)
                excluded_files.append(path_to_regex(path))
            elif path.is_dir():
                inner_iterator(path)

    inner_iterator()
    return excluded_files


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
    b2_sync(config, verbose, dry_run)


if __name__ == "__main__":
    app()
