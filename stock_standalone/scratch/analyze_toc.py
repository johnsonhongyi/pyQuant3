# -*- coding: utf-8 -*-
import os

def recursive_find_items(obj):
    """
    Recursively find all (name, path, type) elements in the nested structure
    """
    items = []
    if isinstance(obj, list):
        for item in obj:
            items.extend(recursive_find_items(item))
    elif isinstance(obj, tuple):
        # Check if it looks like (name, path, item_type)
        if len(obj) == 3 and isinstance(obj[0], str) and isinstance(obj[1], str) and isinstance(obj[2], str):
            # Known PyInstaller types
            valid_types = {'BINARY', 'DATA', 'EXTENSION', 'OPTION', 'PYMODULE', 'PYSOURCE'}
            # PyInstaller also uses 'PYMODULE-1', 'PYMODULE-2' etc.
            if obj[2] in valid_types or obj[2].startswith('PYMODULE') or obj[2].startswith('PYSOURCE'):
                items.append(obj)
            else:
                for sub in obj:
                    items.extend(recursive_find_items(sub))
        else:
            for sub in obj:
                items.extend(recursive_find_items(sub))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            items.extend(recursive_find_items(k))
            items.extend(recursive_find_items(v))
    return items

def main():
    toc_path = r"d:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone\build\ats\Analysis-00.toc"
    if not os.path.exists(toc_path):
        print(f"Error: TOC file not found at {toc_path}")
        return

    with open(toc_path, "r", encoding="utf-8") as f:
        content = f.read()

    try:
        # Evaluate the python tuple structure
        parsed_data = eval(content)
    except Exception as e:
        print(f"Failed to eval: {e}")
        return

    all_items = recursive_find_items(parsed_data)
    print(f"Found {len(all_items)} packed items in total.")

    # Calculate file sizes
    sized_items = []
    for item in all_items:
        name, path, item_type = item[0], item[1], item[2]
        if os.path.exists(path):
            size = os.path.getsize(path)
            sized_items.append((name, path, item_type, size))
        else:
            sized_items.append((name, path, item_type, 0))

    # De-duplicate items based on name and path
    unique_items = {}
    for name, path, item_type, size in sized_items:
        key = (name, path)
        if key not in unique_items or size > unique_items[key][3]:
            unique_items[key] = (name, path, item_type, size)
    
    sized_items = list(unique_items.values())
    sized_items.sort(key=lambda x: x[3], reverse=True)

    print("\n=== Top 20 Largest Files packed by PyInstaller ===")
    print(f"{'Name':<30} | {'Type':<10} | {'Size(MB)':<8} | {'Path'}")
    print("-" * 100)
    for name, path, item_type, size in sized_items[:20]:
        size_mb = size / (1024 * 1024)
        short_name = name if len(name) < 30 else name[:27] + "..."
        print(f"{short_name:<30} | {item_type:<10} | {size_mb:<8.2f} | {path}")

    # Summarize by type
    by_type = {}
    for name, path, item_type, size in sized_items:
        by_type[item_type] = by_type.get(item_type, 0) + size

    print("\n=== Summary by Type ===")
    for item_type, total_size in by_type.items():
        total_size_mb = total_size / (1024 * 1024)
        print(f"Type: {item_type:<12} | Total Size: {total_size_mb:.2f} MB")

if __name__ == "__main__":
    main()
