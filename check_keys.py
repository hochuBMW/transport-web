import json
from collections import Counter

def list_keys(file_path):
    keys = Counter()
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for feature in data.get('features', []):
                props = feature.get('properties', {})
                keys.update(props.keys())
        
        print("Unique keys in properties:")
        for key, count in keys.most_common():
            print(f"{key}: {count}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_keys("d:\\Web\\diplom\\transport-web\\output.geojson")
