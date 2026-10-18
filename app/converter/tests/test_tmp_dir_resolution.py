"""Tests for choosing Planetiler's scratch directory across machines."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import resolve_tmp_dir


def test_another_machines_disk_falls_back_to_the_compose_mount(tmp_path):
    mounted = tmp_path / "planetiler-tmp"
    mounted.mkdir()

    # /mnt/secondPartition exists on the Linux host only.
    assert Path(resolve_tmp_dir("/mnt/secondPartition/planetiler-tmp", mounted)) == mounted


def test_an_existing_directory_is_kept(tmp_path):
    mounted = tmp_path / "planetiler-tmp"
    mounted.mkdir()
    configured = tmp_path / "second-partition" / "planetiler-tmp"
    configured.mkdir(parents=True)

    assert resolve_tmp_dir(str(configured), mounted) == str(configured)


def test_a_directory_whose_parent_exists_is_kept_for_planetiler_to_create(tmp_path):
    mounted = tmp_path / "planetiler-tmp"
    mounted.mkdir()
    configured = tmp_path / "scratch"

    assert resolve_tmp_dir(str(configured), mounted) == str(configured)


def test_nothing_changes_outside_docker(tmp_path):
    # No compose mount: keep what was configured.
    assert resolve_tmp_dir("/mnt/secondPartition/planetiler-tmp", tmp_path / "absent") == (
        "/mnt/secondPartition/planetiler-tmp"
    )


def test_unset_uses_the_mount(tmp_path):
    assert Path(resolve_tmp_dir(None, tmp_path / "planetiler-tmp")) == tmp_path / "planetiler-tmp"
