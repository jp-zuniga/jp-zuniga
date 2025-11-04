"""
Functions for updating the SVG profile card.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lxml.etree import (
    ParseError,
    parse as lxml_parse,
)

from .cache_man import CacheError
from .consts import JUST_LENGTHS, SVG_DIR
from .utils import validate_kwargs

if TYPE_CHECKING:
    from pathlib import Path

    from lxml.etree import _Element as LxmlElem, _ElementTree as LxmlTree


def update_profile_cards(**kwargs: int | str) -> None:
    """
    Update light/dark cards with new data.

    Args:
        kwargs: Keyword arguments corresponding to new stats.

    """

    if not validate_kwargs(**kwargs):
        msg = "All statistics must be provided to update profile card."
        raise ValueError(msg)

    _update_svg("dark_profile_card.svg", **kwargs)
    _update_svg("light_profile_card.svg", **kwargs)


def _update_svg(svg_name: str, **kwargs: int | str) -> None:
    """
    Update SVG file with new data.

    Args:
        svg_name: Image to be updated.
        kwargs:   Keyword arguments corresponding to new stats.

    """

    svg_path: Path = SVG_DIR / svg_name

    try:
        tree: LxmlTree = lxml_parse(svg_path, parser=None)
        _update_elements(tree.getroot(), **kwargs)
        tree.write(svg_path, encoding="utf-8", xml_declaration=True)  # type: ignore[reportCallIssue]
    except (OSError, ParseError) as e:
        msg = f"SVG update failed: {e!s}"
        raise CacheError(msg) from e


def _fmt_thousands(v: int) -> str:
    return f"{v:,}"


def _fmt_total(v: int) -> str:
    return f"−{abs(v):,}" if v < 0 else f"{v:,}"


def _fmt_add(v: int) -> str:
    return f"+{v:,}"


def _fmt_del(v: int) -> str:
    return f"−{v:,}"


def _set_text(root: LxmlElem, element_id: str, text: str) -> None:
    el: Any = root.find(path=f".//*[@id='{element_id}']", namespaces=None)
    if el is None:
        msg = f"Invalid or nonexistent element_id: {element_id!r}"
        raise ValueError(msg)

    el.text = text


def _justify_from_dots(root: LxmlElem, dots_id: str, target_visible_len: int) -> None:
    dots_el: Any = root.find(path=f".//*[@id='{dots_id}']", namespaces=None)
    if dots_el is None:
        msg = f"Invalid or nonexistent dots_id: {dots_id!r}"
        raise ValueError(msg)

    y = dots_el.get("y")
    parent = dots_el.getparent()
    if parent is None:
        return

    children = list(parent)
    try:
        start_idx = children.index(dots_el) + 1
    except ValueError:
        return

    visible_text: list[str] = []
    for child in children[start_idx:]:
        if child.tag.split("}")[-1] != "tspan":
            continue
        if child.get("y") != y:
            break

        text: str = child.text or ""
        if "│" in text:
            break

        visible_text.append(text)

    current_len = len("".join(visible_text))
    needed = max(target_visible_len - current_len, 0)

    dots_el.text = f" {'.' * needed} "


def _update_elements(root: LxmlElem, **kwargs: int | str) -> None:
    """
    Batch update all statistics.

    Args:
        root:   Root XML element of image.
        kwargs: Keyword arguments corresponding to new stats.

    """

    _set_text(root, "age", str(kwargs["age"]))
    _set_text(root, "stars", _fmt_thousands(int(kwargs["stars"])))
    _set_text(root, "repos", _fmt_thousands(int(kwargs["repos"])))
    _set_text(root, "commits", _fmt_thousands(int(kwargs["commits"])))
    _set_text(root, "loc_total", _fmt_total(int(kwargs["loc_total"])))
    _set_text(root, "loc_add", _fmt_add(int(kwargs["loc_add"])))
    _set_text(root, "loc_del", _fmt_del(int(kwargs["loc_del"])))

    for dots_id, target in JUST_LENGTHS.items():
        _justify_from_dots(root, dots_id, target)
