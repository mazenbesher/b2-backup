import re
import time
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import FrozenSet, Iterable, Iterator, Union, Dict

import typer
import yaml
from gitignore_parser import parse_gitignore
from sortedcontainers import SortedDict
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


@dataclass
class File:
    path: Path
    excluded: bool


def is_above_size_limit(path: Path) -> bool:
    if not 'size_limits' in config:
        return False

    for pattern, size in config['size_limits'].items():
        # size e.g.: ">5"
        if re.compile(pattern).match(path.as_posix()) is not None:
            if size[:2] == ">=" and size[2:].isnumeric() and path.stat().st_size >= float(size[2:]) * 1e6:
                return True
            elif size[:1] == ">" and size[1:].isnumeric() and path.stat().st_size > float(size[1:]) * 1e6:
                return True
            elif size[:2] == "<=" and size[2:].isnumeric() and path.stat().st_size <= float(size[2:]) * 1e6:
                return True
            elif size[:1] == "<" and size[1:].isnumeric() and path.stat().st_size < float(size[1:]) * 1e6:
                return True
    return False


def dir_iter(start_dir: Path) -> Iterator[File]:
    def inner_iterator(
        curr_dir: Path = start_dir,
        parents_with_gitignores: FrozenSet = frozenset([]),
    ):
        paths_in_curr_dir = list(curr_dir.iterdir())
        new_parents_with_gitignores = list(parents_with_gitignores)
        if (curr_dir / '.gitignore') in paths_in_curr_dir:
            new_parents_with_gitignores += [curr_dir]

        def matches(path):
            for par in new_parents_with_gitignores:
                if parse_gitignore(par / '.gitignore')(path):
                    return True
            return False

        for path in paths_in_curr_dir:
            if not access(path):
                print(f"Can't access {path}")
                yield File(path=path, excluded=True)
                continue

            global_match: bool = any(c.match(path.as_posix()) is not None for c in global_ignores_regex)
            if global_match or is_above_size_limit(path) or matches(path):
                yield File(path=path, excluded=True)
            elif path.is_dir():
                yield from inner_iterator(path, frozenset(new_parents_with_gitignores))
            else:
                yield File(path=path, excluded=False)

    yield from inner_iterator()


def get_execluded_files(verbose: bool = False) -> ExcludedFiles:
    src_path: Path = Path(config['src_dir'])
    for file in dir_iter(src_path):
        if file.excluded:
            if verbose:
                print(f'excluding {file.path}')
            # remove first part of the path as it is the source
            path = file.path.relative_to(src_path)
            yield path_to_regex(path)


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
    list(get_execluded_files(verbose=True))


@app.command()
def compute_backup_size(
    show_files: bool = typer.Option(False),
    show_largest_files: int = typer.Option(0, help="Number of top largest files to show. 0 to disable."),
):
    size: int = 0
    src_path: Path = Path(config['src_dir'])

    if show_largest_files > 0:
        sizes_dict: SortedDict = SortedDict()  # key: size, value: path as str

    for file in dir_iter(src_path):
        if not file.excluded:
            if show_files:
                print(file.path)
            curr_file_size = file.path.stat().st_size
            size += curr_file_size

            if show_largest_files > 0:
                sizes_dict[curr_file_size] = str(file.path)
                if len(sizes_dict) > show_largest_files:
                    sizes_dict.popitem()

    print(f'{size:>20,} Bytes')
    print(f'{round(size / 1e3):>20,} KB')
    print(f'{round(size / 1e6):>20,} MB')
    print(f'{round(size / 1e9):>20,} GB')

    if show_largest_files > 0:
        pos_pad = len(str(show_largest_files))
        path_pad = max(map(len, sizes_dict.values()))
        for i, (size, path) in enumerate(reversed(list(sizes_dict.items()))):
            print(f'{i+1:>{pos_pad}}. {path:<{path_pad}} {round(size / 1e6):,} MB')


if __name__ == "__main__":
    app()
