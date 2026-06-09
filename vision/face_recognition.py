"""
vision/face_recognition.py — Facial recognition: detect, identify, store, access control
"""
import cv2
import numpy as np
import os
import json
import logging

logger = logging.getLogger(__name__)
from pathlib import Path
from datetime import datetime
from typing import Optional
from deepface import DeepFace
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.config import FACES_DIR, FACE_RECOGNITION_MODEL, FACE_DETECTION_BACKEND, FACE_DISTANCE_THRESHOLD
from core.database import KnownFace, User, AsyncSessionLocal


# ══════════════════════════════════════════════
#  FACE RECOGNIZER
# ══════════════════════════════════════════════
class FaceRecognizer:
    def __init__(self):
        self.embeddings_cache = {}    # person_name → list of embeddings
        self.face_db_path = FACES_DIR
        self.face_db_path.mkdir(parents=True, exist_ok=True)
        self._load_cache()

    def _load_cache(self):
        cache_file = self.face_db_path / "embeddings_cache.json"
        if cache_file.exists():
            try:
                raw = json.loads(cache_file.read_text(encoding="utf-8"))
                self.embeddings_cache = {
                    k: [np.array(v) for v in vecs]
                    for k, vecs in raw.items()
                }
                logger.info("[FaceRec] Loaded %d known faces from JSON cache ✓", len(self.embeddings_cache))
            except Exception as e:
                logger.warning("[FaceRec] Cache load failed: %s", e)
                self.embeddings_cache = {}

    def _save_cache(self):
        cache_file = self.face_db_path / "embeddings_cache.json"
        serializable = {
            k: [v.tolist() if isinstance(v, np.ndarray) else v for v in vecs]
            for k, vecs in self.embeddings_cache.items()
        }
        cache_file.write_text(json.dumps(serializable, indent=2), encoding="utf-8")

    def get_embedding(self, image: np.ndarray) -> Optional[np.ndarray]:
        """Get face embedding from image."""
        try:
            result = DeepFace.represent(
                img_path=image,
                model_name=FACE_RECOGNITION_MODEL,
                detector_backend=FACE_DETECTION_BACKEND,
                enforce_detection=True
            )
            return np.array(result[0]["embedding"])
        except Exception as e:
            logger.warning("[FaceRec] No face detected: %s", e)
            return None

    def cosine_distance(self, a: np.ndarray, b: np.ndarray) -> float:
        return 1 - np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10)

    def identify_face(self, image: np.ndarray) -> dict:
        """Identify who is in the image. Returns best match or 'Unknown'."""
        embedding = self.get_embedding(image)
        if embedding is None:
            return {"name": None, "confidence": 0, "status": "no_face"}

        best_match = None
        best_distance = float("inf")

        for name, embeddings_list in self.embeddings_cache.items():
            for stored_emb in embeddings_list:
                dist = self.cosine_distance(embedding, stored_emb)
                if dist < best_distance:
                    best_distance = dist
                    best_match = name

        if best_distance < FACE_DISTANCE_THRESHOLD:
            confidence = round((1 - best_distance) * 100, 1)
            return {"name": best_match, "confidence": confidence, "status": "identified", "distance": best_distance}
        else:
            return {"name": "Unknown", "confidence": 0, "status": "unknown", "distance": best_distance}

    async def register_face(
        self,
        db: AsyncSession,
        owner: User,
        person_name: str,
        images: list,         # list of np.ndarray
        relation: str = "unknown",
        info: str = "",
        access_level: str = "visitor"
    ) -> KnownFace:
        """Register a new face with multiple images for better accuracy."""
        person_dir = self.face_db_path / f"user_{owner.id}" / person_name
        person_dir.mkdir(parents=True, exist_ok=True)

        embeddings = []
        saved_count = 0

        for i, img in enumerate(images):
            emb = self.get_embedding(img)
            if emb is not None:
                embeddings.append(emb)
                img_path = person_dir / f"img_{i}.jpg"
                cv2.imwrite(str(img_path), img)
                saved_count += 1

        if not embeddings:
            raise ValueError("No valid face detected in provided images")

        # Update cache
        key = f"{owner.id}_{person_name}"
        if key in self.embeddings_cache:
            self.embeddings_cache[key].extend(embeddings)
        else:
            self.embeddings_cache[key] = embeddings
        self._save_cache()

        # Save to DB
        result = await db.execute(
            select(KnownFace).where(
                KnownFace.owner_id == owner.id,
                KnownFace.person_name == person_name
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.image_count += saved_count
            existing.last_seen = datetime.utcnow()
            await db.commit()
            return existing
        else:
            kf = KnownFace(
                owner_id=owner.id,
                person_name=person_name,
                relation=relation,
                info=info,
                embedding_path=str(person_dir),
                image_count=saved_count,
                access_level=access_level
            )
            db.add(kf)
            await db.commit()
            await db.refresh(kf)
            return kf

    async def identify_and_lookup(self, db: AsyncSession, owner: User, image: np.ndarray) -> dict:
        """Identify face and return full person info from DB."""
        match = self.identify_face(image)
        if match["status"] != "identified":
            return match

        name_key = match["name"]
        person_name = name_key.split("_", 1)[-1] if "_" in name_key else name_key

        result = await db.execute(
            select(KnownFace).where(
                KnownFace.owner_id == owner.id,
                KnownFace.person_name == person_name
            )
        )
        kf = result.scalar_one_or_none()
        if kf:
            kf.last_seen = datetime.utcnow()
            await db.commit()
            return {
                **match,
                "person_name": kf.person_name,
                "relation": kf.relation,
                "info": kf.info,
                "access_level": kf.access_level,
                "first_seen": str(kf.first_seen)
            }
        return match


# ══════════════════════════════════════════════
#  LIVE CAMERA FEED + RECOGNITION
# ══════════════════════════════════════════════
class LiveCameraRecognizer:
    def __init__(self):
        self.recognizer = FaceRecognizer()
        self.is_running = False
        self.camera_index = 0

    def start_live_recognition(self, owner_id: int, callback=None, camera_index: int = 0):
        """Start live camera feed with real-time face recognition."""
        import threading

        def _run():
            cap = cv2.VideoCapture(camera_index)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

            self.is_running = True
            frame_count = 0

            while self.is_running:
                ret, frame = cap.read()
                if not ret:
                    break

                frame_count += 1
                # Only process every 10th frame (performance)
                if frame_count % 10 == 0:
                    try:
                        result = self.recognizer.identify_face(frame)
                        if callback:
                            callback(result, frame)

                        # Draw bounding box
                        if result["status"] == "identified":
                            label = f"{result['name']} ({result['confidence']}%)"
                            color = (0, 255, 0)  # green
                        else:
                            label = "Unknown"
                            color = (0, 0, 255)  # red

                        cv2.putText(frame, label, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
                    except Exception as err:
                        import logging
                        logging.getLogger(__name__).error("Exception swallowed: %s", err)
                        raise RuntimeError(f"Exception swallowed: {err}")

                cv2.imshow("JARVIS — Face Recognition", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

            cap.release()
            cv2.destroyAllWindows()
            self.is_running = False

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return t

    def stop(self):
        self.is_running = False

    def capture_frames_for_registration(self, count: int = 10, camera_index: int = 0) -> list:
        """Capture N frames from camera for face registration."""
        cap = cv2.VideoCapture(camera_index)
        frames = []
        print(f"[FaceRec] Capturing {count} frames for registration...")

        while len(frames) < count:
            ret, frame = cap.read()
            if ret:
                frames.append(frame)
                cv2.imshow("Capturing — press Q to stop", frame)
                if cv2.waitKey(100) & 0xFF == ord('q'):
                    break

        cap.release()
        cv2.destroyAllWindows()
        print(f"[FaceRec] Captured {len(frames)} frames ✓")
        return frames


# Singletons
face_recognizer = FaceRecognizer()
live_camera = LiveCameraRecognizer()
