"""Turn every nested API value into spreadsheet cells."""
import json
from pathlib import Path


def route_text(value):
    if isinstance(value, dict):
        return str(value.get("route_name") or value.get("station_name") or "")
    if isinstance(value, list):
        return " → ".join(text for item in value if (text := route_text(item)))
    return ""


def flat_row(row):
    result = {}

    def visit(key, value):
        if isinstance(value, str) and value.strip().startswith(("[", "{")):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, (dict, list)):
                    value = parsed
            except ValueError:
                pass
        if isinstance(value, (dict, list)):
            text = route_text(value)
            if text:
                result[key + "_text"] = text
            entries = value.items() if isinstance(value, dict) else enumerate(value, 1)
            empty = True
            for child, item in entries:
                empty = False
                visit(f"{key}.{child}", item)
            if empty:
                result[key] = ""
        else:
            if key in result:
                raise ValueError("Spreadsheet column collision")
            if isinstance(value, int) and not isinstance(value, bool) and abs(value) >= 10**15:
                value = str(value)
            if isinstance(value, str) and len(value) > 32767:
                for index, offset in enumerate(range(0, len(value), 32767), 1):
                    result[f"{key}.part_{index}"] = value[offset:offset + 32767]
            else:
                result[key] = "" if value is None else value

    for key, value in row.items():
        visit(key, value)
    return result


def table(rows):
    flat = [flat_row(row) for row in rows]
    columns = list(dict.fromkeys(key for row in flat for key in row))
    return columns, [[row.get(key, "") for key in columns] for row in flat]


def export_excel(path, rows, title="Onsite"):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    columns, values = table(rows)
    if len(columns) > 16384 or len(values) > 1048575:
        raise ValueError("Data exceeds Excel sheet limits")
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title
    sheet.append(columns)
    for row in values:
        sheet.append(row)
    for cells in sheet.iter_rows():
        for cell in cells:
            if isinstance(cell.value, str):
                # Preserve IDs/phones and literal text, including leading '='.
                cell.data_type = "s"
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="23374D")
    sheet.freeze_panes = "A2"
    if columns:
        sheet.auto_filter.ref = sheet.dimensions
    for index, name in enumerate(columns, 1):
        width = min(55, max(14, len(name) + 2))
        if name == "Time" or name.endswith("_text"):
            width = 55
        sheet.column_dimensions[get_column_letter(index)].width = width
    target = Path(path)
    temporary = target.with_suffix(".tmp.xlsx")
    workbook.save(temporary)
    temporary.replace(target)
