import pytest
import json
import numpy as np
import sys


@pytest.fixture(autouse=True)
def mock_deepface_deps():
    """Prevent deepface import errors by mocking before import."""
    import unittest.mock

    mock_deepface = unittest.mock.MagicMock()
    # Mock the DeepFace module at sys.modules level so vision.face_recognition
    # can import it without triggering tf-keras dependency errors.
    sys.modules["deepface"] = mock_deepface
    sys.modules["deepface.DeepFace"] = mock_deepface
    # Prevent retinaface from loading
    sys.modules["retinaface"] = unittest.mock.MagicMock()
    yield
    # Clean up after test
    sys.modules.pop("deepface", None)
    sys.modules.pop("deepface.DeepFace", None)
    sys.modules.pop("retinaface", None)


@pytest.fixture
def face_recognizer(tmp_path):
    from vision.face_recognition import FaceRecognizer

    class TestableFaceRecognizer(FaceRecognizer):
        def __init__(self):
            self.embeddings_cache = {}
            self.face_db_path = tmp_path
            self.face_db_path.mkdir(parents=True, exist_ok=True)

    return TestableFaceRecognizer()


class TestFaceRecognitionCache:
    def test_save_and_load_cache(self, face_recognizer, tmp_path):
        cache_file = tmp_path / "embeddings_cache.json"
        face_recognizer.embeddings_cache = {
            "alice": [np.array([0.1, 0.2, 0.3]), np.array([0.4, 0.5, 0.6])],
            "bob": [np.array([0.7, 0.8, 0.9])],
        }
        face_recognizer._save_cache()
        assert cache_file.exists()
        raw = json.loads(cache_file.read_text(encoding="utf-8"))
        assert "alice" in raw
        assert "bob" in raw
        assert raw["alice"] == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        assert raw["bob"] == [[0.7, 0.8, 0.9]]

    def test_load_cache_restores_ndarray(self, face_recognizer, tmp_path):
        cache_file = tmp_path / "embeddings_cache.json"
        cache_file.write_text(json.dumps({
            "carol": [[0.11, 0.22], [0.33, 0.44]],
        }), encoding="utf-8")
        face_recognizer._load_cache()
        assert "carol" in face_recognizer.embeddings_cache
        vecs = face_recognizer.embeddings_cache["carol"]
        assert len(vecs) == 2
        assert isinstance(vecs[0], np.ndarray)
        assert vecs[0].tolist() == [0.11, 0.22]
        assert vecs[1].tolist() == [0.33, 0.44]

    def test_load_cache_missing_file(self, face_recognizer):
        face_recognizer.embeddings_cache = {"existing": []}
        face_recognizer._load_cache()
        assert face_recognizer.embeddings_cache == {"existing": []}

    def test_load_cache_corrupted_file(self, face_recognizer, tmp_path):
        cache_file = tmp_path / "embeddings_cache.json"
        cache_file.write_text("not valid json", encoding="utf-8")
        face_recognizer._load_cache()
        assert face_recognizer.embeddings_cache == {}

    def test_empty_cache_save(self, face_recognizer, tmp_path):
        cache_file = tmp_path / "embeddings_cache.json"
        face_recognizer.embeddings_cache = {}
        face_recognizer._save_cache()
        assert cache_file.exists()
        assert json.loads(cache_file.read_text()) == {}

    def test_cache_file_is_json_not_pickle(self, face_recognizer, tmp_path):
        face_recognizer._save_cache()
        cache_file = tmp_path / "embeddings_cache.json"
        assert cache_file.suffix == ".json"
        assert cache_file.read_text(encoding="utf-8").startswith("{")
