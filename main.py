import re
import time
import sys
from pathlib import Path
from typing import Iterable, Union, Dict

import typer
import yaml
from gitignore_parser import parse_gitignore
from b2sdk.v2 import InMemoryAccountInfo
from b2sdk.v2 import B2Api
from b2sdk.v2 import ScanPoliciesManager
from b2sdk.v2 import parse_sync_folder
from b2sdk.v2 import SyncReport
from b2sdk.v2 import Synchronizer
from b2sdk.v2 import KeepOrDeleteMode, CompareVersionMode, NewerFileSyncMode


config: Dict = None


def check_config():
    # assert all keys are passed
    required_config_keys = [
        'src_dir', 'dst_bucket_name',
        'app_key_id', 'app_key',
    ]
    for key in required_config_keys:
        if not key in config:
            raise ValueError(f'{key} in config is required')

    src_path: Path = Path(config['src_dir'])
    if not src_path.exists():
        raise ValueError(f'src path {src_path} does not exist!')


def load_config():
    global config
    if not Path('config.yaml').exists():
        raise ValueError('No config file!')
    config = yaml.safe_load(Path('config.yaml').read_text())
    check_config()


load_config()
app = typer.Typer()
ExcludedFiles = Iterable[Union[str, re.Pattern]]

global_ignores_regex = []
if 'global_ignores' in config:
    global_ignores_regex = [re.compile(r) for r in config['global_ignores']]


def path_to_regex(path: Path) -> str:
    return path.as_posix().replace('/', '\/').replace('.', '\.')


def access(path: Path) -> bool:
    try:
        path.is_dir()
    except OSError:
        return False
    return True


def get_execluded_files(verbose: bool = False) -> ExcludedFiles:
    src_path: Path = Path(config['src_dir'])

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
            global_match: bool = any(c.match(path.as_posix()) is not None for c in global_ignores_regex)
            if global_match or (has_gitignore and matches(path)):
                if verbose:
                    print(f'excluding {path}')
                # remove first part of the path as it is the source
                path = path.relative_to(src_path)
                yield path_to_regex(path)
            elif path.is_dir():
                yield from inner_iterator(path)

    yield from inner_iterator()


@app.command()
def sync(
    verbose: bool = typer.Option(False),
    dry_run: bool = typer.Option(False),
):
    info = InMemoryAccountInfo()
    b2_api = B2Api(info)
    b2_api.authorize_account(
        "production",
        config['app_key_id'],
        config['app_key'],
    )

    policies_manager = ScanPoliciesManager(
        exclude_all_symlinks=True,
        exclude_file_regexes=get_execluded_files(verbose),
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

    src_path: Path = Path(config['src_dir'])
    dst_bucket_name: str = config['dst_bucket_name']

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
    get_execluded_files(verbose=True)


@app.command()
def compute_backup_size(
    show_files: bool = typer.Option(False),
    show_largest_files: int = typer.Option(0),  # TODO
):
    size: int = 0
    src_path: Path = Path(config['src_dir'])

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
            global_match: bool = any(c.match(path.as_posix()) is not None for c in global_ignores_regex)
            if global_match or (has_gitignore and matches(path)):
                continue
            elif path.is_dir():
                inner_iterator(path)
            else:
                if show_files:
                    print(path)
                size += path.stat().st_size

    inner_iterator()
    print(f'{size:>20,} Bytes')
    print(f'{round(size / 1e3):>20,} KB')
    print(f'{round(size / 1e6):>20,} MB')
    print(f'{round(size / 1e9):>20,} GB')


if __name__ == "__main__":
    app()
