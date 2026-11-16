"""Self-authored, in-memory collection-scope example, not an application.

These functions only calculate IDs. No request, authorization, file export,
database write, background job or deployed service is implemented here.
"""

from dataclasses import dataclass, replace


ORDERS = (
    ("O-101", "pending"),
    ("O-102", "pending"),
    ("O-103", "complete"),
    ("O-104", "pending"),
    ("O-105", "complete"),
    ("O-106", "pending"),
)
PAGE_SIZE = 2


@dataclass(frozen=True)
class View:
    status: str = "pending"
    page: int = 1
    selected: frozenset[str] = frozenset()


def matching_ids(status="pending"):
    return tuple(order_id for order_id, value in ORDERS if value == status)


def page_ids(view):
    start = (view.page - 1) * PAGE_SIZE
    return matching_ids(view.status)[start:start + PAGE_SIZE]


def change_page(view, page):
    if page < 1:
        raise ValueError("page must be positive")
    return replace(view, page=page)


def change_filter(view, status):
    return View(status=status)


def select_row(view, order_id):
    if order_id not in page_ids(view):
        raise ValueError("row is not on the current page")
    return replace(view, selected=view.selected | {order_id})


def select_page(view):
    return replace(view, selected=view.selected | set(page_ids(view)))


def select_matching(view):
    return replace(view, selected=frozenset(matching_ids(view.status)))


def batch_targets(view):
    return tuple(sorted(view.selected))


def export_targets(view):
    return matching_ids(view.status)
