"""资产校验测试夹具"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILLS_DIR = REPO_ROOT / "skills"          # 原子技能
WORKFLOWS_DIR = REPO_ROOT / "workflows"    # 工作流（复合技能）
DOCS_DIR = REPO_ROOT / "docs"

# 每个技能 / 工作流自带的 10 项文档
ASSET_DOCS = [
    "01-usage-manual.md",
    "02-architecture.md",
    "03-flow.md",
    "04-examples.md",
    "05-media.md",
    "06-scenarios.md",
    "07-audience.md",
    "08-value.md",
    "09-test-report.md",
]


def _dirs(base: Path) -> list[Path]:
    if not base.exists():
        return []
    return sorted(d for d in base.iterdir() if d.is_dir())


def atomic_dirs() -> list[Path]:
    """原子技能目录（skills/ 下）。"""
    return _dirs(SKILLS_DIR)


def composite_dirs() -> list[Path]:
    """工作流目录（workflows/ 下）。"""
    return _dirs(WORKFLOWS_DIR)


def all_asset_dirs() -> list[Path]:
    """全部资产目录（原子 + 工作流）。"""
    return atomic_dirs() + composite_dirs()


@pytest.fixture(scope="session")
def skills():
    return atomic_dirs()


@pytest.fixture(scope="session")
def workflows():
    return composite_dirs()


@pytest.fixture(scope="session")
def assets():
    return all_asset_dirs()
