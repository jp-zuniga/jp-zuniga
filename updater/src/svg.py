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

    from lxml.etree import _Element as lxml_elem, _ElementTree as lxml_tree


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
        tree: lxml_tree = lxml_parse(svg_path, parser=None)
        _update_elements(tree.getroot(), **kwargs)
        tree.write(svg_path, encoding="utf-8", xml_declaration=True)  # type: ignore[reportCallIssue]
    except (OSError, ParseError) as e:
        raise CacheError(f"SVG update failed: {e!s}") from e


def _update_elements(root: lxml_elem, **kwargs: int | str) -> None:
    """
    Batch update all statistics.

    Args:
        root:   Root XML element of image.
        kwargs: Keyword arguments corresponding to new stats.

    """

    for element, value in kwargs.items():
        if element == "loc_total":
            continue

        element_value = f"{value:,}" if isinstance(value, int) else str(value)
        dots_count = (
            JUST_LENGTHS[f"{element}_dots"] - len(element_value)
            if element not in ("loc_add", "loc_del")
            else None
        )

        _update_single_element(
            root,
            f"{element}_dots",
            dots_count,
            element,
            element_value,
        )

    loc_total: int = kwargs["loc_total"]  # type: ignore[reportAssignmentType]
    loc_total_str = f"{'−' if loc_total < 0 else ''}{loc_total:,}"
    loc_line_len = len(
        f"{loc_total_str} , +{kwargs['loc_add']:,} , −{kwargs['loc_del']:,}",
    )

    loc_total_dots_count = JUST_LENGTHS["loc_total_dots"] - loc_line_len

    _update_single_element(
        root,
        "loc_total_dots",
        loc_total_dots_count,
        "loc_total",
        loc_total_str,
    )


def _update_single_element(
    root: lxml_elem,
    dots_id: str,
    dots_count: int | None,
    element_id: str,
    element_value: str,
) -> None:
    """
    Update an SVG element and its corresponding justification dots.

    Args:
        root:          Root XML element of image.
        dots_id:       ID of element's justification dots.
        element_id:    ID of element to update.
        element_value: New value of element.
        dots_count:    Amount of justification dots for new value.

    """

    value_element: Any = root.find(
        path=f".//*[@id='{element_id}']",
        namespaces=None,
    )

    if value_element is None:
        msg = "Invalid or nonexistent `element_id`."
        raise ValueError(msg)

    if element_id == "loc_add":
        element_value = f"+{element_value}"
    elif element_id == "loc_del":
        element_value = f"−{element_value}"

    value_element.text = element_value

    if dots_count is None:
        return

    dots_id = f"{element_id}_dots"
    dots_element: Any = root.find(path=f".//*[@id='{dots_id}']", namespaces=None)
    if dots_element is None:
        msg = "Invalid or nonexistent dots field for given `element_id`."
        raise ValueError(msg)

    dots_element.text = f" {'.' * dots_count} "  # type: ignore[reportOperatorIssue]
