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
        _update_single_element(
            root,
            f"{element}_dots",
            element,
            element_value,
            JUST_LENGTHS[f"{element_value}_dots"] - len(element_value),
        )

    new_loc_total = f"{kwargs['loc_total']:,}"
    _update_single_element(
        root,
        "loc_total_dots",
        "loc_total",
        new_loc_total,
        len(
            f"{new_loc_total} , +{kwargs['loc_add']:,} , −{kwargs['loc_del']:,}",
        ),
    )


def _update_single_element(
    root: lxml_elem,
    dots_id: str,
    element_id: str,
    element_value: str,
    dots_count: int,
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

    value_element.text = element_value

    if element_id in ("loc_add", "loc_del"):
        return

    dots_id = f"{element_id}_dots"
    dots_element: Any = root.find(path=f".//*[@id='{dots_id}']", namespaces=None)
    if dots_element is None:
        msg = "Invalid or nonexistent dots field for given `element_id`."
        raise ValueError(msg)

    dots_element.text = f" {'.' * dots_count} "
