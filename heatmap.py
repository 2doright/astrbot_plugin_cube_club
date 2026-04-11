from datetime import datetime, date, timedelta
import re


def parse_map_parameters(message: str) -> tuple[int | None, bool]:
    """Parse `/map` or `/热力图` arguments for optional year and group mode."""
    args = message.split()[1:]
    year = None
    group = False
    for token in args:
        lower = token.lower()
        if lower == "group":
            group = True
            continue

        if re.fullmatch(r"\d{2}", token):
            year = 2000 + int(token)
        elif re.fullmatch(r"\d{4}", token):
            year = int(token)
    return year, group


def build_heatmap_data(
    counts: dict[str, int],
    year: int,
    month: int | None,
    group: bool,
    subject_label: str | None = None,
) -> dict:
    """Prepare heatmap rendering data for monthly or yearly view."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    chart_type = "year" if month is None else "month"
    period_label = f"{year}年" if month is None else f"{year}年{month}月"
    if group:
        title = "社团活跃度"
    else:
        title = f"{subject_label or '个人'} 活跃度"
    subtitle = period_label

    if chart_type == "month":
        start_day = date(year, month, 1)
        week_start = start_day - timedelta(days=(start_day.weekday() + 1) % 7)
        next_month = date(year + (month // 12), (month % 12) + 1, 1)
        final_day = next_month - timedelta(days=1)
        end_day = final_day + timedelta(days=(6 - ((final_day.weekday() + 1) % 7)))
    else:
        start_day = date(year, 1, 1)
        week_start = start_day - timedelta(days=(start_day.weekday() + 1) % 7)
        end_day = date(year, 12, 31)
        end_day = end_day + timedelta(days=(6 - ((end_day.weekday() + 1) % 7)))

    total_weeks = ((end_day - week_start).days // 7) + 1
    cell_size = 18
    gap = 4
    x_spacing = cell_size + gap
    y_spacing = cell_size + gap
    max_count = max(counts.values()) if counts else 0

    if chart_type == "month":
        grid_left = 64
        grid_top = 130
        min_width = 380
    else:
        grid_left = 60
        grid_top = 190
        min_width = 980

    def bucket_level(value: int) -> int:
        if value <= 0:
            return 0
        if max_count <= 4:
            return min(value, 4)
        if value <= max_count * 0.25:
            return 1
        if value <= max_count * 0.5:
            return 2
        if value <= max_count * 0.75:
            return 3
        return 4

    color_map = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]
    cells = []
    day = week_start
    while day <= end_day:
        week_index = (day - week_start).days // 7
        dow = (day.weekday() + 1) % 7
        count = counts.get(day.isoformat(), 0)
        level = bucket_level(count)
        opacity = 1.0 if chart_type == "year" or day.month == month else 0.3
        cells.append({
            "x": grid_left + week_index * x_spacing,
            "y": grid_top + dow * y_spacing,
            "fill": color_map[level],
            "opacity": opacity,
            "tooltip": f"{day.isoformat()}：{count} 次",
            "date": day.isoformat(),
            "count": count,
            "current_period": chart_type == "year" or day.month == month,
        })
        day += timedelta(days=1)

    month_labels = []
    month_label_y = grid_top - 24
    if chart_type == "year":
        for month_index in range(1, 13):
            month_first = date(year, month_index, 1)
            week_index = (month_first - week_start).days // 7
            month_labels.append({
                "x": grid_left + week_index * x_spacing,
                "label": month_first.strftime("%b")
            })

    weekday_labels = []
    if chart_type == "month":
        for index, label in enumerate(["日", "一", "二", "三", "四", "五", "六"]):
            weekday_labels.append({
                "y": grid_top + index * y_spacing + (cell_size / 2) + 4,
                "label": label,
            })

    legend = [{"color": color} for color in color_map]

    width = max(grid_left + total_weeks * x_spacing + 56, min_width)
    height = grid_top + 7 * y_spacing + (100 if chart_type == "month" else 108)

    return {
        "chart_type": chart_type,
        "title": title,
        "subtitle": subtitle,
        "now": now,
        "cells": cells,
        "month_labels": month_labels,
        "month_label_y": month_label_y,
        "weekday_labels": weekday_labels,
        "legend": legend,
        "width": width,
        "height": height,
    }
