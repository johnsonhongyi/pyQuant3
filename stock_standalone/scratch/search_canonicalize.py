import os

target = 'canonicalize_decision_queue_item'
for root, dirs, files in os.walk('.'):
    for file in files:
        if file.endswith('.py'):
            path = os.path.join(root, file)
            try:
                with open(path, encoding='utf-8') as f:
                    content = f.read()
                if target in content:
                    print(f"Found in {path}")
            except Exception:
                pass
