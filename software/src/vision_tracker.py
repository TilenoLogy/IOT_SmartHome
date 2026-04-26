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
        self.model = YOLO("yolov8n.pt")  # Lightweight model
        self.state_lock = threading.Lock()

        self.faces_dir = os.path.join(os.path.dirname(__file__), "..", "faces")
        if not os.path.exists(self.faces_dir):
            os.makedirs(self.faces_dir)

        self.known_face_encodings = []
        self.known_face_names = []
        self._load_known_faces()

        # count_axis: "y" for up/down, "x" for left/right
        self.count_axis = "x"

        # y-axis -> horizontal line at y = line_position
        # x-axis -> vertical line at x = line_position
        self.line_position = 300

        # if count_axis == "y": "down" or "up"
        # if count_axis == "x": "right" or "left"
        self.entering_direction = "right"

        # Robust crossing and occupancy settings
        self.line_deadzone_px = 14
        self.track_event_cooldown_sec = 1.0

        # Performance tuning
        self.show_debug_window = True
        self.infer_every_n_frames = 1
        self.yolo_imgsz = 512
        self.yolo_conf = 0.35
        self.min_face_crop_px = 48
        self.face_match_threshold = 0.70

        # Tracking state
        self.tracked_history = {}          # track_id -> previous center value on selected axis
        self.track_last_side = {}          # track_id -> -1/1 (line side)
        self.track_last_event_time = {}    # track_id -> last enter/exit timestamp
        self.track_in_room = {}            # track_id -> bool
        self.track_to_occupant_key = {}    # track_id -> occupants key

        # Room state separate from identity certainty
        self.present_count = 0
        self.next_occupant_id = 1
        self.unresolved_exit_count = 0
        self.frame_index = 0

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

        if (x2 - x1) < self.min_face_crop_px or (y2 - y1) < self.min_face_crop_px:
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
                    face_distances = face_recognition.face_distance(self.known_face_encodings, encoding)
                    if len(face_distances) > 0:
                        best_idx = face_distances.argmin()
                        if face_distances[best_idx] < self.face_match_threshold:
                            return self.known_face_names[best_idx]

                # Unrecognized face -> save it
                guest_name = f"guest_{track_id}"
                guest_path = os.path.join(self.faces_dir, f"{guest_name}.jpg")
                if not os.path.exists(guest_path):
                    cv2.imwrite(guest_path, face_img)
                    self.known_face_encodings.append(encoding)
                    self.known_face_names.append(guest_name)
                    print(f"Saved new unknown guest: {guest_path}")
                return guest_name

        # No face encoding found; still try saving a fallback snapshot for review.
        guest_name = f"guest_{track_id}"
        guest_path = os.path.join(self.faces_dir, f"{guest_name}.jpg")
        if not os.path.exists(guest_path):
            cv2.imwrite(guest_path, face_img)
            print(f"Saved fallback guest snapshot (no encoding): {guest_path}")

        return f"guest_{track_id}"

    def _resolve_counting_config(self, frame_shape):
        frame_h, frame_w = frame_shape[:2]

        axis = str(self.count_axis).lower().strip()
        if axis not in ("x", "y"):
            axis = "y"

        if axis == "y":
            line_pos = max(0, min(int(self.line_position), frame_h - 1))
            enter_dir = str(self.entering_direction).lower().strip()
            if enter_dir not in ("up", "down"):
                enter_dir = "down"
        else:
            line_pos = max(0, min(int(self.line_position), frame_w - 1))
            enter_dir = str(self.entering_direction).lower().strip()
            if enter_dir not in ("left", "right"):
                enter_dir = "right"

        return axis, line_pos, enter_dir

    def _axis_center(self, box, axis):
        x1, y1, x2, y2 = box
        center_x = (x1 + x2) / 2
        center_y = (y1 + y2) / 2
        return center_y if axis == "y" else center_x

    def _side_of_line(self, value, line_pos):
        if value < line_pos - self.line_deadzone_px:
            return -1
        if value > line_pos + self.line_deadzone_px:
            return 1
        return 0

    def _occupant_name_exists(self, name, must_be_certain=False):
        """Check if an occupant with this name is already in the room."""
        for rec in occupants.values():
            if rec.get("name") == name:
                if must_be_certain and not rec.get("certain", True):
                    continue
                return True
        return False

    def _add_occupant(self, name, certain=True):
        """Add occupant or reconcile an existing name on re-entry.

        Returns:
            (occupant_key, existed_before)
        """
        same_name_keys = [
            key for key, rec in occupants.items()
            if rec.get("name") == name
        ]

        if same_name_keys:
            # Prefer keeping an already-certain record, otherwise keep the oldest one.
            keep_key = None
            for key in same_name_keys:
                if occupants[key].get("certain", True):
                    keep_key = key
                    break
            if keep_key is None:
                keep_key = same_name_keys[0]

            occupants[keep_key]["certain"] = bool(certain)

            # Remove duplicate records of the same person name.
            for key in same_name_keys:
                if key != keep_key:
                    del occupants[key]

            return keep_key, True

        key = f"{self.next_occupant_id}_{name}"
        occupants[key] = {
            "name": name,
            "certain": bool(certain),
            "entered_at": time.time(),
        }
        self.next_occupant_id += 1
        return key, False

    def _remove_occupant_key(self, key):
        if key in occupants:
            del occupants[key]
            return True
        return False

    def _remove_by_name(self, name):
        for key, rec in list(occupants.items()):
            if rec.get("name") == name:
                del occupants[key]
                return True
        return False

    def _mark_all_uncertain(self):
        for rec in occupants.values():
            rec["certain"] = False

    def _cleanup_empty_room_state(self):
        if self.present_count == 0:
            occupants.clear()
            self.unresolved_exit_count = 0

    def get_public_state(self):
        with self.state_lock:
            data = []
            uncertain_present = False
            for key, rec in occupants.items():
                name = rec.get("name", key.split("_", 1)[1] if "_" in key else key)
                certain = bool(rec.get("certain", True))
                if not certain:
                    uncertain_present = True
                data.append({
                    "id": key.split("_", 1)[0],
                    "name": name,
                    "certain": certain,
                })

            return {
                "occupants": data,
                "count": self.present_count,
                "unresolved_exit_count": self.unresolved_exit_count,
                "has_uncertainty": uncertain_present or self.unresolved_exit_count > 0,
            }

    def process_frame(self, frame, do_inference=True):
        frame_h, frame_w = frame.shape[:2]
        axis, line_pos, enter_dir = self._resolve_counting_config(frame.shape)

        if not do_inference:
            # Draw only the counting line on skipped frames to keep UI smooth.
            if axis == "y":
                cv2.line(frame, (0, line_pos), (frame_w, line_pos), (0, 0, 255), 2)
            else:
                cv2.line(frame, (line_pos, 0), (line_pos, frame_h), (0, 0, 255), 2)
            return frame

        # Run YOLO to detect and track people (class 0)
        results = self.model.track(
            frame,
            persist=True,
            classes=[0],
            verbose=False,
            conf=self.yolo_conf,
            imgsz=self.yolo_imgsz,
        )

        if results[0].boxes is not None and results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            track_ids = results[0].boxes.id.int().cpu().numpy()

            for box, track_id in zip(boxes, track_ids):
                x1, y1, x2, y2 = box
                center_axis = self._axis_center(box, axis)
                current_side = self._side_of_line(center_axis, line_pos)
                now = time.time()

                with self.state_lock:
                    previous_side = self.track_last_side.get(track_id, 0)
                    last_event_time = self.track_last_event_time.get(track_id, 0)

                    # Persist useful history for future frame decisions.
                    self.tracked_history[track_id] = center_axis

                    if current_side != 0:
                        self.track_last_side[track_id] = current_side

                    # Ignore non-crossings and deadzone-only movement.
                    if previous_side == 0 or current_side == 0 or previous_side == current_side:
                        pass
                    # Guard against jitter double-triggers.
                    elif now - last_event_time < self.track_event_cooldown_sec:
                        pass
                    else:
                        crossed_positive = previous_side == -1 and current_side == 1
                        crossed_negative = previous_side == 1 and current_side == -1

                        # Positive crossing means down on y-axis, right on x-axis.
                        if axis == "y":
                            entered = crossed_positive if enter_dir == "down" else crossed_negative
                            exited = crossed_negative if enter_dir == "down" else crossed_positive
                        else:
                            entered = crossed_positive if enter_dir == "right" else crossed_negative
                            exited = crossed_negative if enter_dir == "right" else crossed_positive

                        if entered:
                            # Ignore impossible duplicate "enter" event for same track.
                            if self.track_in_room.get(track_id, False):
                                print(f"Ignoring duplicate enter for track {track_id}")
                            else:
                                name = self.recognize_face(frame, box, track_id)
                                # New entrant stays certain even while older occupants are uncertain.
                                occ_key, existed_before = self._add_occupant(name=name, certain=True)
                                self.track_to_occupant_key[track_id] = occ_key
                                self.track_in_room[track_id] = True

                                if existed_before:
                                    # Identity was already present but uncertain/duplicated; reconcile it.
                                    if self.unresolved_exit_count > 0:
                                        self.unresolved_exit_count -= 1
                                    print(f"{name} (ID {track_id}) Re-identified")
                                else:
                                    self.present_count += 1
                                    print(f"{name} (ID {track_id}) Entered")

                        elif exited:
                            # Ignore impossible exit from an empty room.
                            if self.present_count == 0:
                                print(f"Ignoring exit for track {track_id}: room already empty")
                            else:
                                removed = False

                                # First choice: remove by track->occupant mapping (most reliable).
                                occ_key = self.track_to_occupant_key.get(track_id)
                                if occ_key:
                                    removed = self._remove_occupant_key(occ_key)

                                # Second choice: remove by recognized name.
                                if not removed:
                                    name = self.recognize_face(frame, box, track_id)
                                    removed = self._remove_by_name(name)

                                # Fallback: count still decrements, identity becomes uncertain.
                                if not removed:
                                    self.unresolved_exit_count += 1
                                    self._mark_all_uncertain()
                                    print(f"Unresolved exit for track {track_id}; marking occupants uncertain")
                                else:
                                    print(f"Track {track_id} Exited")

                                self.present_count = max(0, self.present_count - 1)
                                self.track_in_room[track_id] = False
                                self.track_to_occupant_key.pop(track_id, None)
                                self._cleanup_empty_room_state()

                        self.track_last_event_time[track_id] = now

                # Draw bounding box and ID/name on frame
                cv2.rectangle(
                    frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2
                )

                disp_name = str(track_id)
                with self.state_lock:
                    occ_key = self.track_to_occupant_key.get(track_id)
                    if occ_key and occ_key in occupants:
                        disp_name = occupants[occ_key].get("name", str(track_id))

                cv2.putText(
                    frame,
                    disp_name,
                    (int(x1), int(y1) - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 0),
                    2,
                )

        # Draw virtual counting line
        if axis == "y":
            cv2.line(frame, (0, line_pos), (frame_w, line_pos), (0, 0, 255), 2)
        else:
            cv2.line(frame, (line_pos, 0), (line_pos, frame_h), (0, 0, 255), 2)

        return frame

    def run(self):
        self.running = True

        while self.running:
            self.camera_connected = False
            print(f"Connecting to ESP32-CAM stream: {self.stream_url}")
            cap = cv2.VideoCapture(self.stream_url)

            # Keep the capture queue short to reduce old-frame lag and spikes.
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

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
                    break  # Break inner loop to try reconnecting

                self.frame_index += 1
                do_inference = (self.frame_index % self.infer_every_n_frames) == 0
                processed_frame = self.process_frame(frame, do_inference=do_inference)

                # For debugging on PC
                if self.show_debug_window:
                    cv2.imshow("Room Tracking", processed_frame)
                    if cv2.waitKey(1) == ord("q"):
                        self.running = False
                        break

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
