#!/usr/bin/env python3
"""Build either Parallax public repository into a deterministic static site."""

from __future__ import annotations

import argparse
import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, unquote, urlsplit, urlunsplit


SITE_TITLES = {
    "atlas": "Parallax Research Atlas",
    "publications": "Parallax Publications",
}
AREA_SLUG = re.compile(
    r"^[a-z0-9]+(?:-[a-z0-9]+)*(?:/[a-z0-9]+(?:-[a-z0-9]+)*)*$"
)
WIKILINK = re.compile(r"\[\[.*?\]\]")
RESERVED_OUTPUTS = {
    PurePosixPath("_headers"),
    PurePosixPath("robots.txt"),
    PurePosixPath("sitemap.xml"),
    PurePosixPath("build-manifest.json"),
    PurePosixPath("assets/site.css"),
}


class BuildError(Exception):
    """A user-facing validation or build failure."""


class BuildArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise BuildError(f"arguments: {message}")


@dataclass
class Page:
    source_label: str
    relative_source: PurePosixPath | None
    output: PurePosixPath
    document: dict[str, Any]
    title: str
    public_id: str | None
    areas: list[str]


@dataclass(frozen=True)
class Area:
    slug: str
    title: str
    parent: str | None
    status: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


def clean_one_line(value: str) -> str:
    return " ".join(value.replace("\r", " ").replace("\n", " ").split())


def run_pandoc(command: list[str], data: str, source_label: str) -> str:
    try:
        result = subprocess.run(
            command,
            input=data,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except FileNotFoundError as exc:
        raise BuildError("pandoc: required binary was not found") from exc
    if result.returncode != 0:
        detail = clean_one_line(result.stderr or result.stdout or "unknown pandoc error")
        raise BuildError(f"{source_label}: pandoc failed: {detail}")
    return result.stdout


def pandoc_version() -> str:
    try:
        result = subprocess.run(
            ["pandoc", "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except FileNotFoundError as exc:
        raise BuildError("pandoc: required binary was not found") from exc
    if result.returncode != 0 or not result.stdout.strip():
        detail = clean_one_line(result.stderr or "could not read version")
        raise BuildError(f"pandoc: {detail}")
    first_line = result.stdout.splitlines()[0].strip()
    match = re.fullmatch(r"pandoc\s+(\d+)\.(\d+)(?:\.(\d+))?.*", first_line)
    if not match or int(match.group(1)) != 3:
        raise BuildError(f"pandoc: version 3.x is required, found {first_line}")
    return first_line


def parse_markdown(markdown: str, source_label: str) -> dict[str, Any]:
    rendered = run_pandoc(
        ["pandoc", "--from=markdown-raw_html", "--to=json"],
        markdown,
        source_label,
    )
    try:
        document = json.loads(rendered)
    except json.JSONDecodeError as exc:
        raise BuildError(f"{source_label}: pandoc returned invalid JSON") from exc
    if not isinstance(document, dict) or not isinstance(document.get("meta"), dict):
        raise BuildError(f"{source_label}: pandoc JSON has no metadata block")
    return document


def stringify_pandoc(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(stringify_pandoc(item) for item in value)
    if not isinstance(value, dict):
        return ""
    kind = value.get("t")
    content = value.get("c")
    if kind in {"Str", "MetaString"} and isinstance(content, str):
        return content
    if kind in {"Space", "SoftBreak", "LineBreak"}:
        return " "
    if kind in {"Code", "Math"} and isinstance(content, list) and content:
        return str(content[-1])
    return stringify_pandoc(content)


def plain_text(value: Any) -> str:
    return " ".join(stringify_pandoc(value).split())


def metadata_scalar(meta: dict[str, Any], key: str, source_label: str) -> str | None:
    if key not in meta:
        return None
    node = meta[key]
    if isinstance(node, dict) and node.get("t") in {"MetaList", "MetaMap"}:
        raise BuildError(f"{source_label}: frontmatter {key} must be a scalar")
    value = plain_text(node)
    return value or None


def metadata_list(meta: dict[str, Any], key: str, source_label: str) -> list[str] | None:
    if key not in meta:
        return None
    node = meta[key]
    if not isinstance(node, dict) or node.get("t") != "MetaList":
        raise BuildError(f"{source_label}: frontmatter {key} must be a list")
    values = [plain_text(item) for item in node.get("c", [])]
    if any(not item for item in values):
        raise BuildError(f"{source_label}: frontmatter {key} contains an empty value")
    return values


def page_title(document: dict[str, Any], source_label: str) -> str:
    meta = document["meta"]
    title = metadata_scalar(meta, "title", source_label)
    if not title:
        for block in document.get("blocks", []):
            if (
                isinstance(block, dict)
                and block.get("t") == "Header"
                and isinstance(block.get("c"), list)
                and block["c"][0] == 1
            ):
                title = plain_text(block["c"][2])
                break
    if not title:
        raise BuildError(f"{source_label}: page has no frontmatter title or level-1 heading")
    if WIKILINK.search(title) or "[[" in title or "]]" in title:
        raise BuildError(f"{source_label}: title contains wikilink markup: {title}")
    return title


def markdown_output(relative: PurePosixPath) -> PurePosixPath:
    if relative.name == "index.md":
        return relative.parent / "index.html"
    return relative.parent / relative.stem / "index.html"


def clean_url_for_markdown(relative: PurePosixPath) -> str:
    output = markdown_output(relative)
    if output == PurePosixPath("index.html"):
        return "/"
    return "/" + output.parent.as_posix().strip("/") + "/"


def clean_url_for_output(output: PurePosixPath) -> str:
    if output == PurePosixPath("index.html"):
        return "/"
    if output.name == "index.html":
        return "/" + output.parent.as_posix().strip("/") + "/"
    return "/" + output.as_posix()


def rewrite_markdown_links(document: dict[str, Any], relative: PurePosixPath) -> None:
    def visit(node: Any) -> None:
        if isinstance(node, list):
            for child in node:
                visit(child)
            return
        if not isinstance(node, dict):
            return
        if node.get("t") == "Link":
            content = node.get("c")
            if isinstance(content, list) and content:
                target = content[-1]
                if isinstance(target, list) and target and isinstance(target[0], str):
                    original = target[0]
                    parsed = urlsplit(original)
                    if (
                        not parsed.scheme
                        and not parsed.netloc
                        and parsed.path
                        and not parsed.path.startswith("/")
                        and parsed.path.lower().endswith(".md")
                    ):
                        decoded = unquote(parsed.path)
                        joined = posixpath.normpath(
                            posixpath.join(relative.parent.as_posix(), decoded)
                        )
                        if joined == ".." or joined.startswith("../"):
                            raise BuildError(
                                f"{relative.as_posix()}: relative Markdown link escapes SRC: {original}"
                            )
                        clean = clean_url_for_markdown(PurePosixPath(joined))
                        target[0] = urlunsplit(
                            ("", "", quote(clean, safe="/-._~"), parsed.query, parsed.fragment)
                        )
        visit(node.get("c"))

    visit(document.get("blocks", []))


def scan_source(src: Path, out: Path) -> list[tuple[PurePosixPath, Path]]:
    files: list[tuple[PurePosixPath, Path]] = []

    def walk(directory: Path, relative: PurePosixPath) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as exc:
            raise BuildError(f"{directory}: cannot read directory: {exc}") from exc
        for entry in entries:
            if entry.name.startswith(".") or entry.name == ".git":
                continue
            path = Path(entry.path)
            rel = relative / entry.name
            if entry.is_symlink():
                raise BuildError(f"{rel.as_posix()}: symlinks are not allowed in SRC")
            try:
                if path.resolve(strict=False) == out:
                    continue
                if entry.is_dir(follow_symlinks=False):
                    walk(path, rel)
                elif entry.is_file(follow_symlinks=False):
                    files.append((rel, path))
                else:
                    raise BuildError(f"{rel.as_posix()}: unsupported non-regular file")
            except OSError as exc:
                raise BuildError(f"{rel.as_posix()}: cannot inspect file: {exc}") from exc

    walk(src, PurePosixPath())
    return files


def clean_output(out: Path) -> None:
    if out.is_symlink():
        raise BuildError(f"{out}: OUT may not be a symlink")
    if out.exists() and not out.is_dir():
        raise BuildError(f"{out}: OUT exists and is not a directory")
    out.mkdir(parents=True, exist_ok=True)
    children = sorted(out.iterdir(), key=lambda item: item.name)
    manifest = out / "build-manifest.json"
    if children and (manifest.is_symlink() or not manifest.is_file()):
        raise BuildError(
            f"{out}: OUT is non-empty and has no build-manifest.json from a previous build"
        )
    for child in children:
        if child.is_symlink() or child.is_file():
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child)
        else:
            raise BuildError(f"{child}: unsupported entry already present in OUT")


def read_json(path: Path, description: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BuildError(f"{path}: invalid {description}: {clean_one_line(str(exc))}") from exc


def load_areas(path: Path) -> dict[str, Area]:
    raw = read_json(path, "area registry JSON")
    if not isinstance(raw, list):
        raise BuildError(f"{path}: area registry must be a JSON list")
    areas: dict[str, Area] = {}
    required = {"slug", "title", "parent", "status"}
    for index, item in enumerate(raw):
        if not isinstance(item, dict) or not required.issubset(item):
            raise BuildError(f"{path}: area entry {index} lacks slug, title, parent, or status")
        slug, title, parent, status = (
            item["slug"],
            item["title"],
            item["parent"],
            item["status"],
        )
        if not isinstance(slug, str) or not AREA_SLUG.fullmatch(slug):
            raise BuildError(f"{path}: invalid area slug at entry {index}: {slug!r}")
        if not isinstance(title, str) or not title.strip():
            raise BuildError(f"{path}: area {slug} has an empty title")
        if parent is not None and (not isinstance(parent, str) or not parent):
            raise BuildError(f"{path}: area {slug} has an invalid parent")
        if status not in {"open", "closed"}:
            raise BuildError(f"{path}: area {slug} status must be open or closed")
        if slug in areas:
            raise BuildError(f"{path}: duplicate area slug {slug}")
        areas[slug] = Area(slug, title.strip(), parent, status)
    for area in areas.values():
        if area.parent is not None and area.parent not in areas:
            raise BuildError(f"{path}: area {area.slug} names unknown parent {area.parent}")
        seen = {area.slug}
        parent = area.parent
        while parent is not None:
            if parent in seen:
                raise BuildError(f"{path}: area hierarchy cycle at {area.slug}")
            seen.add(parent)
            if area.status == "open" and areas[parent].status == "closed":
                raise BuildError(
                    f"{path}: open area {area.slug} has closed ancestor {parent}"
                )
            parent = areas[parent].parent
    return areas


def load_page_areas(path: Path) -> dict[str, list[str]]:
    raw = read_json(path, "page-area map JSON")
    if not isinstance(raw, dict):
        raise BuildError(f"{path}: page-area map must be a JSON object")
    result: dict[str, list[str]] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key:
            raise BuildError(f"{path}: page-area map keys must be non-empty strings")
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise BuildError(f"{path}: page-area map value for {key!r} must be a string list")
        result[key] = value
    return result


def area_is_descendant(candidate: str, ancestor: str, areas: dict[str, Area]) -> bool:
    current: str | None = candidate
    while current is not None:
        if current == ancestor:
            return True
        current = areas[current].parent
    return False


def markdown_link(label: str, url: str) -> str:
    safe_label = label.replace("[", "\\[").replace("]", "\\]")
    return f"[{safe_label}]({url})"


def open_area_children(areas: dict[str, Area]) -> dict[str | None, list[Area]]:
    children: dict[str | None, list[Area]] = {}
    for area in areas.values():
        if area.status == "open":
            children.setdefault(area.parent, []).append(area)
    for siblings in children.values():
        siblings.sort(key=lambda item: (item.title.casefold(), item.slug))
    return children


def area_tree_markdown(children: dict[str | None, list[Area]]) -> list[str]:
    lines: list[str] = []

    def add_children(parent: str | None, depth: int) -> None:
        for area in children.get(parent, []):
            lines.append(
                "    " * depth
                + f"- {markdown_link(area.title, '/areas/' + area.slug + '/')}"
            )
            add_children(area.slug, depth + 1)

    add_children(None, 0)
    return lines


def generated_page(markdown: str, title: str, output: PurePosixPath, label: str) -> Page:
    document = parse_markdown(markdown, label)
    document["meta"]["title"] = {"t": "MetaString", "c": title}
    return Page(label, None, output, document, title, None, [])


def edition_for_output(output: PurePosixPath) -> str | None:
    parts = output.parts
    if len(parts) >= 3 and parts[0] == "editions":
        return parts[1]
    return None


def render_page(
    page: Page,
    destination: Path,
    template: Path,
    site_title: str,
    chrome: dict[str, bool],
) -> None:
    page.document["meta"]["title"] = {"t": "MetaString", "c": page.title}
    command = [
        "pandoc",
        "--from=json",
        "--to=html5",
        "--standalone",
        f"--template={template}",
        "--variable",
        f"site-title={site_title}",
    ]
    if page.title != site_title:
        command.extend(["--variable", "title-suffix=true"])
    edition = edition_for_output(page.output)
    if edition:
        command.extend(["--variable", f"edition-label={edition}"])
    for key, enabled in sorted(chrome.items()):
        if enabled:
            command.extend(["--variable", f"{key}=true"])
    serialized = json.dumps(page.document, ensure_ascii=False, sort_keys=True)
    rendered = run_pandoc(command, serialized, page.source_label)
    write_text(destination, rendered)


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []
        self.has_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "script":
            self.has_script = True
        for key, value in attrs:
            if key.lower() == "href" and value is not None:
                self.hrefs.append(value)


def validate_html(out: Path) -> None:
    root = out.resolve()
    for page in sorted(out.rglob("*.html")):
        parser = LinkCollector()
        try:
            parser.feed(page.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as exc:
            raise BuildError(f"{page}: invalid HTML text: {clean_one_line(str(exc))}") from exc
        if parser.has_script:
            raise BuildError(f"{page}: JavaScript script tag is not allowed")
        for href in parser.hrefs:
            parsed = urlsplit(href)
            if parsed.scheme.lower() == "javascript":
                raise BuildError(f"{page}: JavaScript link is not allowed")
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            decoded = unquote(parsed.path)
            target = root / decoded.lstrip("/") if decoded.startswith("/") else page.parent / decoded
            resolved = target.resolve(strict=False)
            try:
                resolved.relative_to(root)
            except ValueError as exc:
                raise BuildError(f"{page}: internal link escapes OUT: {href}") from exc
            valid = resolved.is_file() or (resolved.is_dir() and (resolved / "index.html").is_file())
            if not valid:
                raise BuildError(f"{page}: broken internal link: {href}")


def reserve_output(
    reserved: dict[PurePosixPath, str], destination: PurePosixPath, source_label: str
) -> None:
    if destination in reserved:
        raise BuildError(
            f"{source_label}: output collision at {destination.as_posix()} with {reserved[destination]}"
        )
    reserved[destination] = source_label


def normalized_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
        raise BuildError(f"{value}: --base-url must be an absolute HTTP(S) URL without query or fragment")
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = BuildArgumentParser(description=__doc__)
    parser.add_argument("--src", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--surface", required=True, choices=sorted(SITE_TITLES))
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--areas", type=Path)
    parser.add_argument("--page-areas", type=Path)
    parser.add_argument("--strict-page-areas", action="store_true")
    return parser.parse_args(argv)


def build(args: argparse.Namespace) -> None:
    script_root = Path(__file__).resolve().parent
    template = script_root / "templates" / "page.html"
    stylesheet = script_root / "assets" / "site.css"
    for required in (template, stylesheet):
        if not required.is_file():
            raise BuildError(f"{required}: required build asset is missing")

    version = pandoc_version()
    try:
        src = args.src.resolve(strict=True)
    except OSError as exc:
        raise BuildError(f"{args.src}: SRC is not a readable directory") from exc
    if not src.is_dir():
        raise BuildError(f"{args.src}: SRC is not a directory")
    out = args.out.resolve(strict=False)
    if src == out:
        raise BuildError(f"{args.out}: OUT must differ from SRC")
    try:
        src.relative_to(out)
    except ValueError:
        pass
    else:
        raise BuildError(f"{args.out}: OUT may not contain SRC")
    base_url = normalized_base_url(args.base_url)
    if args.areas and args.surface != "atlas":
        raise BuildError(f"{args.areas}: --areas is valid only for the atlas surface")

    source_files = scan_source(src, out)
    for rel, _ in source_files:
        if rel.suffix.lower() in {".js", ".mjs", ".cjs"}:
            raise BuildError(f"{rel.as_posix()}: JavaScript files are not allowed")

    area_registry = load_areas(args.areas) if args.areas else {}
    page_area_map = load_page_areas(args.page_areas) if args.page_areas and args.areas else {}

    mapped_stem_sources: dict[str, list[str]] = {}
    for rel, _ in source_files:
        if rel.suffix == ".md" and rel.stem in page_area_map:
            mapped_stem_sources.setdefault(rel.stem, []).append(rel.as_posix())
    for stem, sources in sorted(mapped_stem_sources.items()):
        if len(sources) > 1:
            raise BuildError(
                f"ambiguous page-area stem {stem!r}: " + ", ".join(sorted(sources))
            )

    pages: list[Page] = []
    copies: list[tuple[PurePosixPath, Path]] = []
    reserved: dict[PurePosixPath, str] = {}
    inputs: dict[str, str] = {}
    matched_page_area_keys: set[str] = set()
    for rel, path in source_files:
        inputs[f"src/{rel.as_posix()}"] = sha256_file(path)
        if rel.suffix == ".md":
            try:
                markdown = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise BuildError(f"{rel.as_posix()}: cannot read UTF-8 Markdown") from exc
            document = parse_markdown(markdown, rel.as_posix())
            title = page_title(document, rel.as_posix())
            rewrite_markdown_links(document, rel)
            meta = document["meta"]
            public_id: str | None = None
            assigned: list[str] = []
            if args.areas:
                public_id = metadata_scalar(meta, "public_id", rel.as_posix())
                frontmatter_areas = metadata_list(meta, "areas", rel.as_posix())
                page_area_key: str | None = None
                if frontmatter_areas is not None:
                    assigned = frontmatter_areas
                elif public_id and public_id in page_area_map:
                    page_area_key = public_id
                    assigned = page_area_map[public_id]
                elif rel.as_posix() in page_area_map:
                    page_area_key = rel.as_posix()
                    assigned = page_area_map[rel.as_posix()]
                elif rel.stem in page_area_map:
                    page_area_key = rel.stem
                    assigned = page_area_map[rel.stem]
                if page_area_key is not None:
                    matched_page_area_keys.add(page_area_key)
                for slug in assigned:
                    if slug not in area_registry:
                        raise BuildError(f"{rel.as_posix()}: page names unknown area {slug}")
                if assigned and all(area_registry[slug].status == "closed" for slug in assigned):
                    raise BuildError(f"{rel.as_posix()}: all assigned areas are closed")
            output = markdown_output(rel)
            reserve_output(reserved, output, rel.as_posix())
            pages.append(Page(rel.as_posix(), rel, output, document, title, public_id, assigned))
        else:
            reserve_output(reserved, rel, rel.as_posix())
            copies.append((rel, path))

    unmatched_page_area_keys = sorted(set(page_area_map) - matched_page_area_keys)
    if unmatched_page_area_keys:
        if args.strict_page_areas:
            raise BuildError(
                "unmatched page-area keys: "
                + ", ".join(repr(key) for key in unmatched_page_area_keys)
            )
        for key in unmatched_page_area_keys:
            print(f"warning: unmatched page-area key: {key!r}", file=sys.stderr)

    edition_ids = sorted(
        {
            page.output.parts[1]
            for page in pages
            if len(page.output.parts) >= 3 and page.output.parts[0] == "editions"
        }
    )

    if PurePosixPath("index.html") not in reserved:
        links: list[tuple[str, str]] = []
        if any(page.output == PurePosixPath("latest/index.html") for page in pages):
            links.append(("Latest", "/latest/"))
        links.extend((f"Edition {edition}", f"/editions/{edition}/") for edition in edition_ids)
        if args.areas:
            links.append(("Topics", "/areas/"))
        policies = sorted(
            (
                (page.title, clean_url_for_output(page.output))
                for page in pages
                if page.relative_source is not None
                and len(page.relative_source.parts) == 1
                and page.relative_source.name != "index.md"
            ),
            key=lambda item: (item[0].casefold(), item[1]),
        )
        links.extend(policies)
        body = [f"# {SITE_TITLES[args.surface]}", "", "Public site index.", ""]
        body.extend(f"- {markdown_link(label, url)}" for label, url in links)
        body.append("")
        page = generated_page(
            "\n".join(body), SITE_TITLES[args.surface], PurePosixPath("index.html"), "generated:index"
        )
        reserve_output(reserved, page.output, page.source_label)
        pages.append(page)

    if edition_ids and PurePosixPath("editions/index.html") not in reserved:
        body = ["# Editions", ""]
        body.extend(
            f"- {markdown_link(edition, f'/editions/{edition}/')}" for edition in edition_ids
        )
        body.append("")
        page = generated_page(
            "\n".join(body), "Editions", PurePosixPath("editions/index.html"), "generated:editions"
        )
        reserve_output(reserved, page.output, page.source_label)
        pages.append(page)

    if args.areas:
        open_areas = [area for area in area_registry.values() if area.status == "open"]
        area_children = open_area_children(area_registry)
        index_body = ["# Topics", "", "Open research areas:", ""]
        index_body.extend(area_tree_markdown(area_children))
        index_body.append("")
        index_page = generated_page(
            "\n".join(index_body), "Topics", PurePosixPath("areas/index.html"), "generated:areas"
        )
        reserve_output(reserved, index_page.output, index_page.source_label)
        pages.append(index_page)
        source_pages = [page for page in pages if page.relative_source is not None]
        for area in sorted(open_areas, key=lambda item: item.slug):
            members = []
            for page in source_pages:
                open_assignments = [
                    slug for slug in page.areas if area_registry[slug].status == "open"
                ]
                if any(area_is_descendant(slug, area.slug, area_registry) for slug in open_assignments):
                    members.append(page)
            members.sort(key=lambda item: (item.title.casefold(), clean_url_for_output(item.output)))
            body = [f"# {area.title}", ""]
            if area.parent is not None:
                parent = area_registry[area.parent]
                body.append(
                    "Parent topic: "
                    + markdown_link(parent.title, "/areas/" + parent.slug + "/")
                )
                body.append("")
            children = area_children.get(area.slug, [])
            if children:
                body.append("Sub-topics:")
                body.append("")
                body.extend(
                    f"- {markdown_link(child.title, '/areas/' + child.slug + '/')}"
                    for child in children
                )
                body.append("")
            if members:
                body.append("Pages in this area and its open sub-areas:")
                body.append("")
                body.extend(
                    f"- {markdown_link(member.title, clean_url_for_output(member.output))}"
                    for member in members
                )
            else:
                body.append("No pages are currently assigned to this area.")
            body.append("")
            output = PurePosixPath("areas") / PurePosixPath(area.slug) / "index.html"
            hub = generated_page(
                "\n".join(body), area.title, output, f"generated:area:{area.slug}"
            )
            reserve_output(reserved, hub.output, hub.source_label)
            pages.append(hub)

    for special in RESERVED_OUTPUTS:
        reserve_output(reserved, special, f"generated:{special.as_posix()}")

    clean_output(out)
    for rel, source in copies:
        destination = out / rel.as_posix()
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    stylesheet_destination = out / "assets" / "site.css"
    stylesheet_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(stylesheet, stylesheet_destination)

    planned = set(reserved)
    chrome = {
        "has-latest": PurePosixPath("latest/index.html") in planned,
        "has-editions": PurePosixPath("editions/index.html") in planned,
        "has-topics": args.surface == "atlas" and bool(args.areas),
        "has-corrections": PurePosixPath("corrections-removal/index.html") in planned,
        "has-license": PurePosixPath("LICENSE") in planned,
        "has-citation": PurePosixPath("CITATION/index.html") in planned,
    }
    for page in sorted(pages, key=lambda item: item.output.as_posix()):
        render_page(page, out / page.output.as_posix(), template, SITE_TITLES[args.surface], chrome)

    headers = """/*
  Content-Security-Policy: default-src 'self'
  X-Content-Type-Options: nosniff
  Referrer-Policy: no-referrer
  X-Frame-Options: DENY
"""
    write_text(out / "_headers", headers)

    html_outputs = sorted(
        path.relative_to(out).as_posix() for path in out.rglob("*.html") if path.is_file()
    )
    sitemap_urls = [base_url + clean_url_for_output(PurePosixPath(path)) for path in html_outputs]
    sitemap_lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sitemap_lines.extend(f"  <url><loc>{html.escape(url)}</loc></url>" for url in sitemap_urls)
    sitemap_lines.extend(["</urlset>", ""])
    write_text(out / "sitemap.xml", "\n".join(sitemap_lines))
    write_text(
        out / "robots.txt",
        f"User-agent: *\nAllow: /\nSitemap: {base_url}/sitemap.xml\n",
    )

    validate_html(out)

    inputs["@builder/build.py"] = sha256_file(Path(__file__).resolve())
    inputs["@builder/templates/page.html"] = sha256_file(template)
    inputs["@builder/assets/site.css"] = sha256_file(stylesheet)
    if args.areas:
        inputs["@config/areas.json"] = sha256_file(args.areas)
    if args.page_areas and args.areas:
        inputs["@config/page-areas.json"] = sha256_file(args.page_areas)
    output_hashes = {
        path.relative_to(out).as_posix(): sha256_file(path)
        for path in sorted(out.rglob("*"))
        if path.is_file() and path.name != "build-manifest.json"
    }
    manifest: dict[str, Any] = {
        "format": 1,
        "pandoc_version": version,
        "surface": args.surface,
        "base_url": base_url,
        "unmatched_page_area_keys": unmatched_page_area_keys,
        "inputs": dict(sorted(inputs.items())),
        "outputs": dict(sorted(output_hashes.items())),
        "manifest_self_hash_scope": (
            "sha256 of canonical manifest JSON before the build-manifest.json output entry is added"
        ),
    }
    basis = (json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    manifest["outputs"]["build-manifest.json"] = sha256_bytes(basis)
    write_text(
        out / "build-manifest.json",
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
        build(args)
    except BuildError as exc:
        print(f"error: {clean_one_line(str(exc))}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("error: build interrupted", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
