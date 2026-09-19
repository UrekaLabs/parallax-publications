from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest


BUILD_ROOT = Path(__file__).resolve().parents[1]
BUILD = BUILD_ROOT / "build.py"


def run_build(
    src: Path,
    out: Path,
    surface: str = "atlas",
    *extra: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(BUILD),
            "--src",
            str(src),
            "--out",
            str(out),
            "--surface",
            surface,
            "--base-url",
            f"https://{'atlas' if surface == 'atlas' else 'parallax'}.example.test",
            *extra,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def write_base_fixture(src: Path) -> None:
    (src / "editions" / "2026-10").mkdir(parents=True)
    (src / "docs").mkdir()
    (src / ".git").mkdir()
    (src / ".hidden.md").write_text("# Hidden\n", encoding="utf-8")
    (src / ".git" / "config").write_text("not published\n", encoding="utf-8")
    (src / "LICENSE").write_text("Synthetic license\n", encoding="utf-8")
    (src / "data.json").write_text('{"ok": true}\n', encoding="utf-8")
    (src / "CITATION.md").write_text("# Citation Guide\n", encoding="utf-8")
    (src / "corrections-removal.md").write_text("# Corrections and Removal\n", encoding="utf-8")
    (src / "latest").mkdir()
    (src / "latest" / "index.md").write_text(
        "# Latest\n\nSee [the edition](../editions/2026-10/index.md).\n",
        encoding="utf-8",
    )
    (src / "editions" / "2026-10" / "index.md").write_text(
        "# Edition 2026-10\n\nSee [One](../../docs/one.md).\n",
        encoding="utf-8",
    )
    (src / "docs" / "one.md").write_text(
        """---
title: Plain One
---
# Ignored Heading

Raw HTML is disabled: <em>not markup</em>.

| A | B |
|---|---|
| 1 | 2 |

A note.[^1]

[^1]: Synthetic footnote.
""",
        encoding="utf-8",
    )


def test_build_is_deterministic_and_complete(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    write_base_fixture(src)
    first, second = tmp_path / "one", tmp_path / "two"

    result = run_build(src, first, "publications")
    assert result.returncode == 0, result.stderr
    result = run_build(src, second, "publications")
    assert result.returncode == 0, result.stderr
    assert tree_hashes(first) == tree_hashes(second)

    assert (first / "index.html").is_file()
    assert (first / "docs" / "one" / "index.html").is_file()
    assert (first / "editions" / "index.html").is_file()
    assert (first / "LICENSE").read_text(encoding="utf-8") == "Synthetic license\n"
    assert (first / "data.json").is_file()
    assert not (first / ".hidden.md").exists()
    assert not list(first.rglob("*.md"))

    edition = (first / "editions" / "2026-10" / "index.html").read_text(encoding="utf-8")
    assert 'href="/docs/one/"' in edition
    assert "Edition 2026-10" in edition
    page = (first / "docs" / "one" / "index.html").read_text(encoding="utf-8")
    assert "Plain One — Parallax Publications" in page
    assert "title: Plain One" not in page
    assert "<table>" in page
    assert "footnote" in page.lower()
    assert "<em>not markup</em>" not in page
    assert "&lt;em&gt;" in page
    assert "<script" not in page.lower()

    headers = (first / "_headers").read_text(encoding="utf-8")
    assert "default-src 'self'" in headers
    assert "X-Content-Type-Options: nosniff" in headers
    assert "Referrer-Policy: no-referrer" in headers
    assert "X-Frame-Options: DENY" in headers
    assert "https://parallax.example.test/docs/one/" in (
        first / "sitemap.xml"
    ).read_text(encoding="utf-8")
    manifest = json.loads((first / "build-manifest.json").read_text(encoding="utf-8"))
    assert manifest["pandoc_version"].startswith("pandoc 3.")
    assert "src/docs/one.md" in manifest["inputs"]
    assert "docs/one/index.html" in manifest["outputs"]
    assert "build-manifest.json" in manifest["outputs"]


def test_nonempty_non_build_output_is_refused_without_deletion(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    write_base_fixture(src)
    out = tmp_path / "not-a-build"
    (out / "nested").mkdir(parents=True)
    keep = out / "nested" / "keep.txt"
    keep.write_text("user data\n", encoding="utf-8")

    result = run_build(src, out, "publications")

    assert result.returncode == 1
    assert str(out) in result.stderr
    assert "OUT" in result.stderr and "build-manifest.json" in result.stderr
    assert len(result.stderr.splitlines()) == 1
    assert keep.read_text(encoding="utf-8") == "user data\n"
    assert sorted(path.relative_to(out).as_posix() for path in out.rglob("*")) == [
        "nested",
        "nested/keep.txt",
    ]


def test_empty_output_and_previous_build_are_allowed(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    write_base_fixture(src)
    out = tmp_path / "out"
    out.mkdir()

    first = run_build(src, out, "publications")
    assert first.returncode == 0, first.stderr
    assert (out / "build-manifest.json").is_file()

    stale = out / "stale.txt"
    stale.write_text("remove me\n", encoding="utf-8")
    second = run_build(src, out, "publications")
    assert second.returncode == 0, second.stderr
    assert not stale.exists()
    assert (out / "build-manifest.json").is_file()


@pytest.mark.parametrize(
    ("surface", "site_title"),
    [
        ("atlas", "Parallax Research Atlas"),
        ("publications", "Parallax Publications"),
    ],
)
def test_home_page_title_does_not_repeat_site_title(
    tmp_path: Path, surface: str, site_title: str
) -> None:
    src = tmp_path / "src"
    src.mkdir()
    result = run_build(src, tmp_path / "out", surface)
    assert result.returncode == 0, result.stderr

    home = (tmp_path / "out" / "index.html").read_text(encoding="utf-8")
    assert f"<title>{site_title}</title>" in home
    assert f"{site_title} — {site_title}" not in home


def test_area_hubs_include_open_descendants_and_mapping(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "editions" / "2026-10").mkdir(parents=True)
    (src / "editions" / "2026-10" / "index.md").write_text("# Edition\n", encoding="utf-8")
    (src / "direct.md").write_text(
        "---\ntitle: Direct\npublic_id: atlas-direct\nareas: [oversight]\n---\n\n# Direct\n",
        encoding="utf-8",
    )
    (src / "mapped.md").write_text(
        "---\ntitle: Mapped\npublic_id: atlas-mapped\n---\n\n# Mapped\n",
        encoding="utf-8",
    )
    areas = tmp_path / "areas.json"
    areas.write_text(
        json.dumps(
            [
                {"slug": "oversight", "title": "Oversight", "parent": None, "status": "open"},
                {
                    "slug": "oversight/iran-contra",
                    "title": "Iran-Contra",
                    "parent": "oversight",
                    "status": "open",
                },
                {"slug": "closed", "title": "Closed", "parent": None, "status": "closed"},
            ]
        ),
        encoding="utf-8",
    )
    mapping = tmp_path / "map.json"
    mapping.write_text(json.dumps({"atlas-mapped": ["oversight/iran-contra"]}), encoding="utf-8")
    out = tmp_path / "out"

    result = run_build(src, out, "atlas", "--areas", str(areas), "--page-areas", str(mapping))
    assert result.returncode == 0, result.stderr
    parent = (out / "areas" / "oversight" / "index.html").read_text(encoding="utf-8")
    child = (out / "areas" / "oversight" / "iran-contra" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "/direct/" in parent and "/mapped/" in parent
    assert "/mapped/" in child and "/direct/" not in child
    assert not (out / "areas" / "closed").exists()
    assert 'href="/areas/"' in (out / "mapped" / "index.html").read_text(encoding="utf-8")


def write_area_registry(path: Path) -> None:
    path.write_text(
        json.dumps(
            [
                {"slug": "oversight", "title": "Oversight", "parent": None, "status": "open"},
                {
                    "slug": "oversight/subtopic",
                    "title": "Subtopic",
                    "parent": "oversight",
                    "status": "open",
                },
                {"slug": "closed", "title": "Closed", "parent": None, "status": "closed"},
            ]
        ),
        encoding="utf-8",
    )


def test_page_area_map_falls_back_to_filename_stem(tmp_path: Path) -> None:
    src = tmp_path / "src"
    (src / "nested").mkdir(parents=True)
    (src / "nested" / "atlas-stem.md").write_text(
        "---\ntitle: Stem Mapped\n---\n\n# Stem Mapped\n", encoding="utf-8"
    )
    areas = tmp_path / "areas.json"
    write_area_registry(areas)
    mapping = tmp_path / "map.json"
    mapping.write_text(json.dumps({"atlas-stem": ["oversight/subtopic"]}), encoding="utf-8")
    out = tmp_path / "out"

    result = run_build(src, out, "atlas", "--areas", str(areas), "--page-areas", str(mapping))

    assert result.returncode == 0, result.stderr
    parent = (out / "areas" / "oversight" / "index.html").read_text(encoding="utf-8")
    child = (out / "areas" / "oversight" / "subtopic" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "/nested/atlas-stem/" in parent
    assert "/nested/atlas-stem/" in child
    manifest = json.loads((out / "build-manifest.json").read_text(encoding="utf-8"))
    assert manifest["unmatched_page_area_keys"] == []


@pytest.mark.parametrize(
    ("mapped_area", "needle"),
    [
        ("closed", "closed"),
        ("missing", "unknown area"),
    ],
)
def test_stem_fallback_preserves_area_validation(
    tmp_path: Path, mapped_area: str, needle: str
) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "atlas-stem.md").write_text("# Stem Mapped\n", encoding="utf-8")
    areas = tmp_path / "areas.json"
    write_area_registry(areas)
    mapping = tmp_path / "map.json"
    mapping.write_text(json.dumps({"atlas-stem": [mapped_area]}), encoding="utf-8")

    result = run_build(
        src,
        tmp_path / "out",
        "atlas",
        "--areas",
        str(areas),
        "--page-areas",
        str(mapping),
    )

    assert result.returncode == 1
    assert "atlas-stem.md" in result.stderr
    assert needle in result.stderr.lower()


def test_mapped_duplicate_stem_is_ambiguous(tmp_path: Path) -> None:
    src = tmp_path / "src"
    (src / "one").mkdir(parents=True)
    (src / "two").mkdir()
    (src / "one" / "shared.md").write_text("# First\n", encoding="utf-8")
    (src / "two" / "shared.md").write_text("# Second\n", encoding="utf-8")
    areas = tmp_path / "areas.json"
    write_area_registry(areas)
    mapping = tmp_path / "map.json"
    mapping.write_text(json.dumps({"shared": ["oversight"]}), encoding="utf-8")

    result = run_build(
        src,
        tmp_path / "out",
        "atlas",
        "--areas",
        str(areas),
        "--page-areas",
        str(mapping),
    )

    assert result.returncode == 1
    assert "ambiguous" in result.stderr.lower()
    assert "one/shared.md" in result.stderr
    assert "two/shared.md" in result.stderr


def test_unmatched_page_area_keys_warn_manifest_and_strict_fail(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "page.md").write_text("# Page\n", encoding="utf-8")
    areas = tmp_path / "areas.json"
    write_area_registry(areas)
    mapping = tmp_path / "map.json"
    mapping.write_text(
        json.dumps({"z-missing": ["oversight"], "a-missing": ["oversight"]}),
        encoding="utf-8",
    )

    out = tmp_path / "out"
    result = run_build(src, out, "atlas", "--areas", str(areas), "--page-areas", str(mapping))
    assert result.returncode == 0, result.stderr
    assert result.stderr.splitlines() == [
        "warning: unmatched page-area key: 'a-missing'",
        "warning: unmatched page-area key: 'z-missing'",
    ]
    manifest = json.loads((out / "build-manifest.json").read_text(encoding="utf-8"))
    assert manifest["unmatched_page_area_keys"] == ["a-missing", "z-missing"]

    strict = run_build(
        src,
        tmp_path / "strict-out",
        "atlas",
        "--areas",
        str(areas),
        "--page-areas",
        str(mapping),
        "--strict-page-areas",
    )
    assert strict.returncode == 1
    assert "unmatched" in strict.stderr.lower()
    assert "a-missing" in strict.stderr and "z-missing" in strict.stderr


@pytest.mark.parametrize(
    ("area_value", "needle"),
    [
        ("closed", "closed"),
        ("missing", "unknown area"),
    ],
)
def test_invalid_area_assignment_fails_with_file(
    tmp_path: Path, area_value: str, needle: str
) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "bad.md").write_text(
        f"---\ntitle: Bad\nareas: [{area_value}]\n---\n\n# Bad\n", encoding="utf-8"
    )
    areas = tmp_path / "areas.json"
    areas.write_text(
        json.dumps([{"slug": "closed", "title": "Closed", "parent": None, "status": "closed"}]),
        encoding="utf-8",
    )
    result = run_build(src, tmp_path / "out", "atlas", "--areas", str(areas))
    assert result.returncode == 1
    assert "bad.md" in result.stderr
    assert needle in result.stderr.lower()
    assert len(result.stderr.splitlines()) == 1


def test_wikilink_title_and_symlink_are_rejected(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "bad.md").write_text(
        "---\ntitle: '[[concept/x|Bad]]'\n---\n\n# Safe Heading\n", encoding="utf-8"
    )
    result = run_build(src, tmp_path / "wikilink")
    assert result.returncode == 1
    assert "bad.md" in result.stderr and "title" in result.stderr.lower()

    (src / "bad.md").unlink()
    target = tmp_path / "outside.txt"
    target.write_text("outside\n", encoding="utf-8")
    (src / "linked.txt").symlink_to(target)
    result = run_build(src, tmp_path / "symlink")
    assert result.returncode == 1
    assert "linked.txt" in result.stderr and "symlink" in result.stderr.lower()


def test_without_area_registry_ignores_area_metadata(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "page.md").write_text(
        "---\ntitle: Page\nareas: legacy-scalar\n---\n\n# Page\n", encoding="utf-8"
    )
    result = run_build(src, tmp_path / "out")
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "out" / "areas").exists()
