import requests
import sys
import os

url = 'http://localhost:8000/update_floor_plan'

if len(sys.argv) > 1:
    image_path = sys.argv[1]
    if os.path.exists(image_path):
        with open(image_path, 'rb') as f:
            files = {'file': (os.path.basename(image_path), f, 'image/jpeg')}
            print(f"Uploading image {image_path} to {url}...")
            r = requests.post(url, files=files)
            print("Response:", r.json())
    else:
        print(f"Error: Image {image_path} does not exist.")
else:
    print("Please provide the path to an image file.")
    print("Usage: python test_vision_ingest.py <path_to_image>")
