from math import ceil


def normalize_page(value, default=1):
    try:
        page = int(value)
    except (TypeError, ValueError):
        return default
    return page if page > 0 else default


def normalize_direction(value, default="asc"):
    normalized = (value or default).strip().lower()
    return normalized if normalized in {"asc", "desc"} else default


def paginate_query(query, *, page=1, per_page=10):
    safe_per_page = per_page if per_page > 0 else 10
    total = query.order_by(None).count()
    pages = ceil(total / safe_per_page) if total else 1
    current_page = min(max(page, 1), pages)
    items = query.offset((current_page - 1) * safe_per_page).limit(safe_per_page).all()
    start_index = 0 if total == 0 else ((current_page - 1) * safe_per_page) + 1
    end_index = min(current_page * safe_per_page, total)
    return {
        "items": items,
        "page": current_page,
        "per_page": safe_per_page,
        "total": total,
        "pages": pages,
        "start_index": start_index,
        "end_index": end_index,
        "has_prev": total > 0 and current_page > 1,
        "has_next": total > 0 and current_page < pages,
    }


def paginate_items(items, *, page=1, per_page=10):
    safe_per_page = per_page if per_page > 0 else 10
    total = len(items)
    pages = ceil(total / safe_per_page) if total else 1
    current_page = min(max(page, 1), pages)
    start = (current_page - 1) * safe_per_page
    end = start + safe_per_page
    page_items = items[start:end]
    start_index = 0 if total == 0 else start + 1
    end_index = min(current_page * safe_per_page, total)
    return {
        "items": page_items,
        "page": current_page,
        "per_page": safe_per_page,
        "total": total,
        "pages": pages,
        "start_index": start_index,
        "end_index": end_index,
        "has_prev": total > 0 and current_page > 1,
        "has_next": total > 0 and current_page < pages,
    }


def build_page_window(page, pages, radius=2):
    if pages <= 0:
        return []
    start = max(1, page - radius)
    end = min(pages, page + radius)
    return list(range(start, end + 1))
