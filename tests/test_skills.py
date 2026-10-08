"""multi-shop-ops-zh 原子技能资产校验

校验 skills/ 下每个原子技能的资产完整性、提示词结构与契约一致性。
不调用任何模型，无需 API Key。
"""
from __future__ import annotations

import json
import re

import pytest

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
ASSET_DOCS = [
    "01-usage-manual.md", "02-architecture.md", "03-flow.md", "04-examples.md",
    "05-media.md", "06-scenarios.md", "07-audience.md", "08-value.md",
    "09-test-report.md",
]

PROMPT_REQUIRED_SECTIONS = ["角色", "输入", "输出格式", "工作原则", "禁止事项", "合规"]
ATOMIC_MD_SECTIONS = [
    "元信息", "输入规格", "输出规格", "能力描述", "使用步骤", "边界", "合规声明",
]


def all_skill_dirs():
    if not SKILLS_DIR.exists():
        return []
    return sorted(d for d in SKILLS_DIR.iterdir() if d.is_dir())


SKILL_DIRS = all_skill_dirs()


def _read(path):
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("sk_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_four_pieces(sk_dir):
    """技能四件套必须齐全。"""
    for fname in ["SKILL.md", "prompt.txt", "schema.json"]:
        assert (sk_dir / fname).exists(), f"{sk_dir.name} 缺少 {fname}"
    assert (sk_dir / "examples").is_dir(), f"{sk_dir.name} 缺少 examples 目录"


@pytest.mark.parametrize("sk_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_examples_exist(sk_dir):
    """示例文件必须存在。"""
    assert (sk_dir / "examples" / "input.json").exists(), f"{sk_dir.name} 缺少示例输入"
    assert (sk_dir / "examples" / "output.md").exists(), f"{sk_dir.name} 缺少示例输出"


@pytest.mark.parametrize("sk_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_has_readme(sk_dir):
    """每个技能必须有独立的 README.md。"""
    assert (sk_dir / "README.md").exists(), f"{sk_dir.name} 缺少 README.md"


@pytest.mark.parametrize("sk_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_has_own_docs(sk_dir):
    """每个技能必须有独立的 docs/ 目录，且含 10 项交付物。"""
    docs = sk_dir / "docs"
    assert docs.is_dir(), f"{sk_dir.name} 缺少 docs/ 目录"
    missing = [d for d in ASSET_DOCS if not (docs / d).exists()]
    assert not missing, f"{sk_dir.name} docs/ 缺少: {missing}"
    assert (docs / "assets" / "overview.svg").exists(), f"{sk_dir.name} 缺少 docs/assets/overview.svg"


@pytest.mark.parametrize("sk_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_docs_not_empty(sk_dir):
    """技能级文档不得为空。"""
    docs = sk_dir / "docs"
    for d in ASSET_DOCS:
        p = docs / d
        if p.exists():
            assert len(p.read_text(encoding="utf-8").strip()) > 200, f"{sk_dir.name}/{d} 内容过少"


@pytest.mark.parametrize("sk_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_prompt_required_sections(sk_dir):
    """prompt.txt 必须包含全部必需区块。"""
    prompt = _read(sk_dir / "prompt.txt")
    missing = [s for s in PROMPT_REQUIRED_SECTIONS if s not in prompt]
    assert not missing, f"{sk_dir.name} prompt.txt 缺少区块: {missing}"


@pytest.mark.parametrize("sk_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_prompt_length(sk_dir):
    """prompt.txt 长度应在合理范围。"""
    prompt = _read(sk_dir / "prompt.txt")
    length = len(prompt)
    assert length >= 300, f"{sk_dir.name} prompt 过短: {length} 字"
    assert length <= 6000, f"{sk_dir.name} prompt 过长: {length} 字"


@pytest.mark.parametrize("sk_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_prompt_forbidden_section(sk_dir):
    """禁止事项区块必须非空。"""
    prompt = _read(sk_dir / "prompt.txt")
    idx = prompt.find("禁止事项")
    assert idx != -1, f"{sk_dir.name} 缺少禁止事项区块"
    tail = prompt[idx:]
    assert "❌" in tail or "-" in tail, f"{sk_dir.name} 禁止事项为空"


@pytest.mark.parametrize("sk_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_prompt_compliance_section(sk_dir):
    """合规区块必须说明 AI 标识与人工审核。"""
    prompt = _read(sk_dir / "prompt.txt")
    idx = prompt.find("合规")
    assert idx != -1, f"{sk_dir.name} 缺少合规区块"
    tail = prompt[idx:]
    assert "AI" in tail, f"{sk_dir.name} 合规区块缺少 AI 标识说明"


@pytest.mark.parametrize("sk_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_md_required_sections(sk_dir):
    """SKILL.md 必须包含必需段落，且声明 atomic。"""
    content = _read(sk_dir / "SKILL.md")
    missing = [s for s in ATOMIC_MD_SECTIONS if s not in content]
    assert not missing, f"{sk_dir.name} SKILL.md 缺少段落: {missing}"
    assert "`atomic`" in content, f"{sk_dir.name} 未声明 type: atomic"


@pytest.mark.parametrize("sk_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_schema_valid_json(sk_dir):
    """schema.json 必须合法且结构完整。"""
    data = json.loads(_read(sk_dir / "schema.json"))
    for key in ["skill_id", "name", "input", "output", "constraints"]:
        assert key in data, f"{sk_dir.name} schema 缺少 {key}"
    assert "required" in data["input"], f"{sk_dir.name} input 缺少 required"
    assert "required" in data["output"], f"{sk_dir.name} output 缺少 required"
    assert data["constraints"].get("external_api_required") is False, (
        f"{sk_dir.name} 不应依赖外部 API"
    )


@pytest.mark.parametrize("sk_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_schema_matches_skill_md(sk_dir):
    """schema.json 的输出字段必须出现在 SKILL.md 中。"""
    schema = json.loads(_read(sk_dir / "schema.json"))
    md = _read(sk_dir / "SKILL.md")
    for field in schema["output"]["required"]:
        assert field in md, f"{sk_dir.name} SKILL.md 未提及输出字段 {field}"


@pytest.mark.parametrize("sk_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_inputs_documented(sk_dir):
    """schema 的输入字段必须在 prompt.txt 中有说明。"""
    schema = json.loads(_read(sk_dir / "schema.json"))
    prompt = _read(sk_dir / "prompt.txt")
    for field in schema["input"]["required"]:
        assert field in prompt, f"{sk_dir.name} prompt.txt 未说明输入字段 {field}"


def test_no_api_key_leaked():
    """仓库内不得出现 API Key。"""
    patterns = [
        r"sk-[A-Za-z0-9]{20,}",
        r"(DEEPSEEK|OPENAI)_API_KEY\s*=\s*\S+",
    ]
    for f in REPO_ROOT.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix not in {".md", ".txt", ".json", ".yaml", ".yml", ".svg"}:
            continue
        if ".git" in f.parts or ".pytest_cache" in f.parts:
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pat in patterns:
            m = re.search(pat, text)
            assert not m, f"{f} 疑似泄漏密钥: {m.group(0)[:20]}"


def test_no_executable_scripts():
    """纯提示词资产不应包含 .py 实现脚本（测试文件除外）。"""
    forbidden = []
    for f in REPO_ROOT.rglob("*.py"):
        rel = f.relative_to(REPO_ROOT)
        parts = rel.parts
        if "tests" in parts:
            continue
        if f.name in ("conftest.py",):
            continue
        forbidden.append(str(rel))
    assert not forbidden, f"发现不应存在的实现脚本: {forbidden}"
