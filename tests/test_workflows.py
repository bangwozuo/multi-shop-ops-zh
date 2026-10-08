"""multi-shop-ops-zh 工作流（复合技能）校验

工作流即复合技能：与原子技能同规范（四件套），但物理上独立放在 workflows/ 下。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
WORKFLOWS_DIR = REPO_ROOT / "workflows"

ASSET_DOCS = [
    "01-usage-manual.md", "02-architecture.md", "03-flow.md", "04-examples.md",
    "05-media.md", "06-scenarios.md", "07-audience.md", "08-value.md",
    "09-test-report.md",
]

REQUIRED_SECTIONS = [
    "元信息", "编排的原子技能", "步骤链路", "步骤明细",
    "输入规格", "输出规格", "错误处理", "验收标准",
]


def all_flow_dirs():
    if not WORKFLOWS_DIR.exists():
        return []
    return sorted(d for d in WORKFLOWS_DIR.iterdir() if d.is_dir())


def atomic_names():
    names = set()
    if SKILLS_DIR.exists():
        for d in SKILLS_DIR.iterdir():
            if d.is_dir():
                names.add(d.name)
    return names


FLOWS = all_flow_dirs()
ATOMICS = atomic_names()


@pytest.mark.parametrize("d", FLOWS, ids=lambda p: p.name)
def test_flow_required_sections(d):
    """工作流 SKILL.md 必须包含必需段落。"""
    content = (d / "SKILL.md").read_text(encoding="utf-8")
    missing = [s for s in REQUIRED_SECTIONS if s not in content]
    assert not missing, f"{d.name} 缺少段落: {missing}"


@pytest.mark.parametrize("d", FLOWS, ids=lambda p: p.name)
def test_flow_declares_composite(d):
    """工作流必须声明 type: composite。"""
    content = (d / "SKILL.md").read_text(encoding="utf-8")
    assert "`composite`" in content, f"{d.name} 未声明 type: composite"


@pytest.mark.parametrize("d", FLOWS, ids=lambda p: p.name)
def test_flow_has_mermaid(d):
    """工作流必须含 Mermaid DAG 图。"""
    content = (d / "SKILL.md").read_text(encoding="utf-8")
    assert "```mermaid" in content, f"{d.name} 缺少 Mermaid 图"
    assert "flowchart" in content, f"{d.name} Mermaid 图非 flowchart"
    assert content.count("```") % 2 == 0, f"{d.name} 代码块围栏未闭合"


@pytest.mark.parametrize("d", FLOWS, ids=lambda p: p.name)
def test_flow_has_steps(d):
    """步骤明细表必须非空。"""
    content = (d / "SKILL.md").read_text(encoding="utf-8")
    idx = content.find("步骤明细")
    assert idx != -1
    tail = content[idx:idx + 3000]
    assert "| 1 |" in tail, f"{d.name} 步骤明细表为空"


@pytest.mark.parametrize("d", FLOWS, ids=lambda p: p.name)
def test_flow_references_existing_atomics(d):
    """工作流引用的原子技能目录必须存在。"""
    content = (d / "SKILL.md").read_text(encoding="utf-8")
    refs = re.findall(r"\.\./\.\./skills/([a-z0-9\-]+)/", content)
    for ref in refs:
        assert ref in ATOMICS, f"{d.name} 引用不存在的原子技能 {ref}"


@pytest.mark.parametrize("d", FLOWS, ids=lambda p: p.name)
def test_flow_four_pieces(d):
    """工作流同样要有四件套。"""
    for fname in ["SKILL.md", "prompt.txt", "schema.json"]:
        assert (d / fname).exists(), f"{d.name} 缺少 {fname}"
    assert (d / "examples" / "input.json").exists(), f"{d.name} 缺少示例输入"
    assert (d / "examples" / "output.md").exists(), f"{d.name} 缺少示例输出"


@pytest.mark.parametrize("d", FLOWS, ids=lambda p: p.name)
def test_flow_has_readme_and_docs(d):
    """工作流必须有独立 README 与 docs/（10 项）。"""
    assert (d / "README.md").exists(), f"{d.name} 缺少 README.md"
    docs = d / "docs"
    assert docs.is_dir(), f"{d.name} 缺少 docs/ 目录"
    missing = [x for x in ASSET_DOCS if not (docs / x).exists()]
    assert not missing, f"{d.name} docs/ 缺少: {missing}"
    assert (docs / "assets" / "overview.svg").exists(), f"{d.name} 缺少 docs/assets/overview.svg"


def test_flow_count():
    """工作流数量校验。"""
    assert len(FLOWS) == 5, (
        f"工作流数量不符：期望 5，实际 {len(FLOWS)}"
    )
