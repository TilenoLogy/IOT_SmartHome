import cv2
import threading
import time
import os
import face_recognition
from ultralytics import YOLO

# Global state for occupants
occupants = {}

class VisionTracker:
    def __init__(self, stream_url="http://192.168.137.118:81/stream"):
        self.stream_url = stream_url
        self.running = False
        self.camera_connected = False
        self.model = YOLO('yolov8n.pt') # Lightweight model
        
        self.faces_dir = os.path.join(os.path.dirname(__file__), "..", "faces")
        if not os.path.exists(self.faces_dir):
            os.makedirs(self.faces_dir)
            
        self.known_face_encodings = []
        self.known_face_names = []
        self._load_known_faces()
        
        # Virtual line (Y coordinate) for counting. Adjust this based on camera view
        self.line_y = 300 
        self.tracked_history = {} # id -> list of previous y positions
        
    def _load_known_faces(self):
        print("Loading known faces...")
        self.known_face_encodings = []
        self.known_face_names = []
        
        for filename in os.listdir(self.faces_dir):
            if filename.endswith(".jpg") or filename.endswith(".png"):
                filepath = os.path.join(self.faces_dir, filename)
                name = os.path.splitext(filename)[0]
                try:
                    image = face_recognition.load_image_file(filepath)
                    encodings = face_recognition.face_encodings(image)
                    if encodings:
                        self.known_face_encodings.append(encodings[0])
                        self.known_face_names.append(name)
                        print(f"Loaded face for: {name}")
                except Exception as e:
                    print(f"Failed to load {filename}: {e}")

    def recognize_face(self, frame, box, track_id):
        x1, y1, x2, y2 = map(int, box)
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        
        face_img = frame[y1:y2, x1:x2]
        if face_img.size == 0:
            return f"guest_{track_id}"
            
        rgb_face = cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB)
        
        # Try to find faces in the detected person's bounding box
        face_locations = face_recognition.face_locations(rgb_face)
        
        if face_locations:
            # We assume there is only one face (the person being tracked)
            encodings = face_recognition.face_encodings(rgb_face, face_locations)
            if encodings:
                encoding = encodings[0]
                if len(self.known_face_encodings) > 0:
                    matches = face_recognition.compare_faces(self.known_face_encodings, encoding, tolerance=0.5)
                    if True in matches:
                        first_match_index = matches.index(True)
                        return self.known_face_names[first_match_index]
                
                # Unrecognized face -> save it
                guest_name = f"guest_{track_id}"
                guest_path = os.path.join(self.faces_dir, f"{guest_name}.jpg")
                if not os.path.exists(guest_path):
                    cv2.imwrite(guest_path, face_img)
                    self.known_face_encodings.append(encoding)
                    self.known_face_names.append(guest_name)
                    print(f"Saved new unknown guest: {guest_path}")
                return guest_name
        
        return f"guest_{track_id}"

    def process_frame(self, frame):
        # Run YOLO to detect and track people (class 0)
        results = self.model.track(frame, persist=True, classes=[0], verbose=False)
        
        if results[0].boxes is not None and results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            track_ids = results[0].boxes.id.int().cpu().numpy()
            
            for box, track_id in zip(boxes, track_ids):
                # Calculate center y of the bounding box
                y1, y2 = box[1], box[3]
                center_y = (y1 + y2) / 2
                
                name = "Unknown"
                if track_id in self.tracked_history:
                    last_y = self.tracked_history[track_id]
                    
                    # Crossing line upwards (entering)
                    if last_y > self.line_y and center_y <= self.line_y:
                        name = self.recognize_face(frame, box, track_id)
                        keys_to_remove = [k for k in occupants.keys() if k.split('_')[0] == str(track_id)]
                        for k in keys_to_remove:
                            del occupants[k]
                        print(f"{name} (ID {track_id}) Exited")
                        
                    # Crossing line downwards (leaving)
                    elif last_y < self.line_y and center_y >= self.line_y:
                        name = self.recognize_face(frame, box, track_id)
                        occupants[f"{track_id}_{name}"] = True
                        print(f"{name} (ID {track_id}) Entered")
                
                self.tracked_history[track_id] = center_y
                
                # Draw bounding box and ID on the frame for debugging
                x1, x2 = box[0], box[2]
                cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
                
                # Find matching occupant to display name or ID
                disp_name = str(track_id)
                for occ in occupants.keys():
                    if occ.startswith(f"{track_id}_"):
                        disp_name = occ.split("_", 1)[1]
                        break
                        
                cv2.putText(frame, disp_name, (int(x1), int(y1) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # Draw the virtual counting line
        cv2.line(frame, (0, self.line_y), (frame.shape[1], self.line_y), (0, 0, 255), 2)
        return frame

    def run(self):
        self.running = True
        
        while self.running:
            self.camera_connected = False
            print(f"Connecting to ESP32-CAM stream: {self.stream_url}")
            cap = cv2.VideoCapture(self.stream_url)
            
            # Check if camera opened correctly
            if cap.isOpened():
                self.camera_connected = True
                print("Successfully connected to ESP32-CAM stream!")
            else:
                print("Failed to open stream. Retrying in 5 seconds...")
                time.sleep(5)
                continue
                
            while self.running and cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    print("Failed to read frame, stream might have disconnected.")
                    self.camera_connected = False
                    time.sleep(1)
                    break # Break inner loop to try reconnecting
                    
                processed_frame = self.process_frame(frame)
                
                # For debugging on PC
                cv2.imshow('Room Tracking', processed_frame)
                    
            cap.release()
            
            if self.running:
                # Wait before trying to reconnect to avoid spamming
                time.sleep(5)
                
        cv2.destroyAllWindows()
        
    def stop(self):
        self.running = False

def start_tracker():
    tracker = VisionTracker()
    tracker_thread = threading.Thread(target=tracker.run, daemon=True)
    tracker_thread.start()
    return tracker
