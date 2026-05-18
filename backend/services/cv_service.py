import cv2
import numpy as np
import uuid

class CVService:
    def __init__(self):
        pass

    def get_grid_position(self, cx: int, cy: int, width: int, height: int) -> str:
        """Determines a rough grid position string based on center coordinates."""
        col = "center"
        if cx < width / 3:
            col = "left"
        elif cx > 2 * width / 3:
            col = "right"
            
        row = "middle"
        if cy < height / 3:
            row = "top"
        elif cy > 2 * height / 3:
            row = "bottom"
            
        if row == "middle" and col == "center":
            return "center"
        return f"{row}-{col}"

    def extract_room_geometry(self, file_bytes: bytes, image_width: int, image_height: int) -> list[dict]:
        """
        Uses OpenCV to extract deterministic room bounding boxes from the floor plan image.
        """
        print(f"[CV_SERVICE] Extracting geometry from image ({image_width}x{image_height})...")
        
        # Convert bytes to numpy array then to cv2 image
        np_arr = np.frombuffer(file_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        if img is None:
            raise ValueError("Could not decode image with OpenCV.")
            
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Apply threshold to find dark lines on white background
        # Or adaptive thresholding
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
        
        # Morphological operations to close small gaps in walls
        kernel = np.ones((5, 5), np.uint8)
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        
        # Find contours
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        regions = []
        min_area = (image_width * image_height) * 0.005 # At least 0.5% of total area
        max_area = (image_width * image_height) * 0.8 # At most 80% of total area
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if min_area < area < max_area:
                x, y, w, h = cv2.boundingRect(contour)
                cx, cy = x + w // 2, y + h // 2
                
                grid_pos = self.get_grid_position(cx, cy, image_width, image_height)
                
                regions.append({
                    "id": f"room_{uuid.uuid4().hex[:8]}",
                    "x": cx,
                    "y": cy,
                    "width": w,
                    "height": h,
                    "box": {"x1": x, "y1": y, "x2": x + w, "y2": y + h},
                    "grid_position": grid_pos,
                    "area": area
                })
        
        print(f"[CV_SERVICE] Found {len(regions)} geometric regions.")
        return regions

cv_service = CVService()
