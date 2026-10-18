"""Apply adaptive rate-column visibility to the live InStock DataTables template."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
import sys


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"Expected one {label} anchor, found {count}")
    return source.replace(old, new, 1)


def patch_template(source: str) -> str:
    if "__instockAdaptiveReturnsV1" in source:
        raise ValueError("Adaptive return-column patch is already present")

    helper = r'''        // __instockAdaptiveReturnsV1: show at least the columns that fit,
        // and retain every return period that contains data in this dataset.
        let adaptiveDataKey = '';
        let adaptiveMaxReturnDay = 0;
        function updateAdaptiveReturnColumns(settings) {
            const json = settings.json;
            if (!json || !Array.isArray(json.data)) return;
            const api = new $.fn.dataTable.Api(settings);
            const fields = api.columns().dataSrc().toArray();
            const rateColumns = [];
            fields.forEach(function(field, index) {
                const match = /^rate_(\d+)$/.exec(String(field));
                if (match) rateColumns.push({index: index, day: Number(match[1]), field: String(field)});
            });
            if (!rateColumns.length) return;

            const activeDate = $('.date-picker').val() || dateParam;
            const key = String(nameParam || '') + '|' + String(activeDate || '');
            if (adaptiveDataKey !== key) {
                adaptiveDataKey = key;
                adaptiveMaxReturnDay = 0;
            }
            let pageMaxReturnDay = 0;
            json.data.forEach(function(row) {
                rateColumns.forEach(function(column) {
                    const value = row[column.field];
                    if (value !== null && value !== undefined && String(value).trim() !== '') {
                        pageMaxReturnDay = Math.max(pageMaxReturnDay, column.day);
                    }
                });
            });
            adaptiveMaxReturnDay = Math.max(adaptiveMaxReturnDay, pageMaxReturnDay);

            const firstRateIndex = rateColumns[0].index;
            function headerWidth(index, fallback) {
                const header = api.column(index).header();
                const width = header ? header.getBoundingClientRect().width : 0;
                return width > 0 ? width : fallback;
            }
            let fixedWidth = 0;
            for (let index = 0; index < firstRateIndex; index++) {
                fixedWidth += headerWidth(index, 100);
            }
            const bodyWidth = settings.nScrollBody && settings.nScrollBody.clientWidth
                ? settings.nScrollBody.clientWidth
                : Math.floor(document.documentElement.clientWidth * 0.75);
            const rateWidth = headerWidth(firstRateIndex, 100);
            const fittingReturnColumns = Math.max(1, Math.floor((bodyWidth - fixedWidth) / rateWidth));
            const visibleReturnDay = Math.min(rateColumns.length,
                Math.max(fittingReturnColumns, adaptiveMaxReturnDay));

            let visibilityChanged = false;
            rateColumns.forEach(function(column) {
                const shouldShow = column.day <= visibleReturnDay;
                const apiColumn = api.column(column.index);
                if (apiColumn.visible() !== shouldShow) {
                    apiColumn.visible(shouldShow, false);
                    visibilityChanged = true;
                }
            });
            if (visibilityChanged) api.columns.adjust();
        }

'''
    source = replace_once(
        source,
        "        const myTable = $('#dynamic-table').DataTable({",
        helper + "        const myTable = $('#dynamic-table').DataTable({",
        "DataTables initialization",
    )
    source = replace_once(
        source,
        '            "bAutoWidth": false,',
        '            "bAutoWidth": false,\n'
        '            "preDrawCallback": function(settings) { updateAdaptiveReturnColumns(settings); },',
        "pre-draw callback",
    )
    source = replace_once(
        source,
        "                    data.date = $('.date-picker').val() || dateParam;",
        "                    data.date = $('.date-picker').val() || dateParam;\n"
        "                    // Keep DataTables' positional search fields; drop unused metadata.\n"
        "                    data.columns = data.columns.map(function(column) {\n"
        "                        return {search: {value: column.search.value || ''}};\n"
        "                    });",
        "compact column-search request",
    )
    source = replace_once(
        source,
        "        $(document).off('click.stockNameLink');",
        "        const allExportColumns = myTable.columns().indexes().toArray();\n"
        "        let adaptiveResizeTimer = null;\n"
        "        $(window).off('resize.instockAdaptiveReturns').on('resize.instockAdaptiveReturns', function() {\n"
        "            window.clearTimeout(adaptiveResizeTimer);\n"
        "            adaptiveResizeTimer = window.setTimeout(function() {\n"
        "                if ($.fn.dataTable.isDataTable('#dynamic-table')) {\n"
        "                    updateAdaptiveReturnColumns(myTable.settings()[0]);\n"
        "                }\n"
        "            }, 120);\n"
        "        });\n\n"
        "        $(document).off('click.stockNameLink');",
        "resize handler and full-column export list",
    )
    # Keep exports complete even when future, empty return columns are hidden.
    for name in ("copy", "csv", "print"):
        source = replace_once(
            source,
            f'"extend": "{name}",',
            f'"extend": "{name}",\n'
            '                "exportOptions": {"columns": allExportColumns},',
            f"{name} export columns",
        )
    return source


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("template", type=Path)
    parser.add_argument("backup", type=Path)
    args = parser.parse_args()
    original = args.template.read_bytes()
    decoded = original.decode("utf-8")
    updated = patch_template(decoded).encode("utf-8")
    args.backup.parent.mkdir(parents=True, exist_ok=True)
    if args.backup.exists():
        raise FileExistsError(f"Refusing to overwrite backup: {args.backup}")
    checksum_path = args.backup.with_name(args.backup.name + ".sha256")
    if checksum_path.exists():
        raise FileExistsError(f"Refusing to overwrite checksum: {checksum_path}")
    shutil.copy2(args.template, args.backup)
    checksum_path.write_text(hashlib.sha256(original).hexdigest() + "\n", encoding="ascii")
    try:
        temporary = args.template.with_name(args.template.name + ".adaptive.tmp")
        if temporary.exists():
            raise FileExistsError(f"Refusing to overwrite temporary file: {temporary}")
        shutil.copy2(args.template, temporary)
        with temporary.open("wb") as target:
            target.write(updated)
        temporary.replace(args.template)
    except BaseException:
        args.template.write_bytes(original)
        raise
    print("Adaptive return columns installed; original template backed up.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)
