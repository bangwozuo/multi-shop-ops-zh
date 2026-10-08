"""multi-shop-ops-zh 交付物完整性校验"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
KNOWLEDGE_DIR = REPO_ROOT / "knowledge"
CONNECTORS_DIR = REPO_ROOT / "connectors"

REQUIRED_DOCS = [
    "01-architecture.md",
    "02-workflow.md",
    "03-scenarios.md",
    "04-usage.md",
    "05-examples.md",
    "06-recording-script.md",
    "07-test-report.md",
]

REQUIRED_ROOT_FILES = [
    "README.md",
    "employee.md",
    "package.yaml",
    "LICENSE",
    "CHANGELOG.md",
    "requirements.txt",
]


@pytest.mark.parametrize("doc", REQUIRED_DOCS)
def test_docs_exist(doc):
    """员工级必需文档必须存在。"""
    assert (DOCS_DIR / doc).exists(), f"缺少文档 {doc}"


@pytest.mark.parametrize("f", REQUIRED_ROOT_FILES)
def test_root_files_exist(f):
    """根目录必需文件必须存在。"""
    assert (REPO_ROOT / f).exists(), f"缺少根文件 {f}"


def test_quality_files_exist():
    """质量文件必须存在。"""
    assert (REPO_ROOT / "quality" / "baseline.md").exists()
    assert (REPO_ROOT / "quality" / "tracking_log.md").exists()


def test_knowledge_rag_wiki_structure():
    """知识库必须是 RAG wiki 结构。"""
    assert (KNOWLEDGE_DIR / "README.md").exists(), "缺少 knowledge/README.md"
    assert (KNOWLEDGE_DIR / "RAG-接入指南.md").exists(), "缺少 RAG 接入指南"
    assert (KNOWLEDGE_DIR / "template.md").exists(), "缺少单文件模板"
    wiki = KNOWLEDGE_DIR / "wiki"
    assert (wiki / "index.md").exists(), "缺少 wiki/index.md"
    assert (wiki / "_template.md").exists(), "缺少 wiki/_template.md"
    assert (wiki / "entries").is_dir(), "缺少 wiki/entries/ 目录"
    entries = list((wiki / "entries").glob("*.md"))
    assert len(entries) >= 5, f"wiki 词条过少：{len(entries)}"


def test_connectors_structured():
    """连接器目录必须结构化：索引 + 合规清单 + 至少一个连接器说明。"""
    assert (CONNECTORS_DIR / "README.md").exists(), "缺少 connectors/README.md"
    assert (CONNECTORS_DIR / "COMPLIANCE.md").exists(), "缺少 connectors/COMPLIANCE.md"
    docs = [p for p in CONNECTORS_DIR.glob("*.md")
            if p.name not in ("README.md", "COMPLIANCE.md")]
    assert docs, "connectors/ 下没有任何连接器说明文件"


def test_compliance_declares_redlines():
    """合规清单必须声明红线。"""
    content = (CONNECTORS_DIR / "COMPLIANCE.md").read_text(encoding="utf-8")
    for kw in ["红线", "官方 API", "人工审核"]:
        assert kw in content, f"COMPLIANCE.md 缺少关键内容：{kw}"


def test_mermaid_fences_paired_in_docs():
    """所有文档中的 Mermaid 代码块必须成对闭合（含技能级 docs）。"""
    targets = list(DOCS_DIR.glob("*.md"))
    for base in ("skills", "workflows"):
        d = REPO_ROOT / base
        if d.exists():
            targets += list(d.glob("*/docs/*.md"))
            targets += list(d.glob("*/README.md"))
    for doc in targets:
        content = doc.read_text(encoding="utf-8")
        assert content.count("```") % 2 == 0, f"{doc} 代码块围栏未闭合"


def test_readme_links_resolve():
    """根 README 中的本地链接必须指向存在的文件（目录链接除外）。"""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    links = re.findall(r"\]\(([^)#][^)]*?)\)", readme)
    for link in links:
        if link.startswith(("http://", "https://", "mailto:")):
            continue
        target = (REPO_ROOT / link).resolve()
        assert target.exists(), f"README 链接失效: {link}"


def test_requirements_minimal():
    """依赖必须精简（仅 pytest）。"""
    content = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    lines = [
        ln.strip()
        for ln in content.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    assert len(lines) <= 2, f"依赖过多：{lines}"
    for ln in lines:
        assert "pytest" in ln.lower(), f"发现非测试依赖：{ln}"
