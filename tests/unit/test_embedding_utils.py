"""Tests for memory.embedding_utils — shared embedding serialization."""

import numpy as np
import struct
import unittest
from memory.embedding_utils import serialize_embedding, deserialize_embedding, cosine_similarity


class TestSerializeEmbedding(unittest.TestCase):
    def test_numpy_roundtrip(self):
        emb = np.array([0.1, 0.2, 0.3], dtype=np.float32)
        blob = serialize_embedding(emb)
        restored = deserialize_embedding(blob)
        self.assertTrue(np.allclose(emb, restored))

    def test_list_roundtrip(self):
        emb = [0.5, 0.6, 0.7, 0.8]
        blob = serialize_embedding(emb)
        restored = deserialize_embedding(blob)
        self.assertTrue(np.allclose(emb, restored))

    def test_tuple_roundtrip(self):
        emb = (0.9, 1.0, 1.1)
        blob = serialize_embedding(emb)
        restored = deserialize_embedding(blob)
        self.assertTrue(np.allclose(emb, restored))

    def test_struct_pack_compatible(self):
        """Output must be compatible with struct.pack format for cross-store migration."""
        emb = [0.1, 0.2, 0.3]
        blob = serialize_embedding(emb)
        expected = struct.pack("3f", *emb)
        self.assertEqual(blob, expected)

    def test_empty_vector(self):
        emb = np.array([], dtype=np.float32)
        blob = serialize_embedding(emb)
        self.assertEqual(blob, b"")
        restored = deserialize_embedding(blob)
        self.assertEqual(len(restored), 0)

    def test_high_dimensional(self):
        emb = np.random.rand(768).astype(np.float32)
        blob = serialize_embedding(emb)
        restored = deserialize_embedding(blob)
        self.assertTrue(np.allclose(emb, restored))
        self.assertEqual(len(blob), 768 * 4)


class TestCosineSimilarity(unittest.TestCase):
    def test_orthogonal(self):
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([0.0, 1.0], dtype=np.float32)
        self.assertAlmostEqual(cosine_similarity(a, b), 0.0)

    def test_identical(self):
        a = np.array([1.0, 0.0], dtype=np.float32)
        self.assertAlmostEqual(cosine_similarity(a, a), 1.0)

    def test_opposite(self):
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([-1.0, 0.0], dtype=np.float32)
        self.assertAlmostEqual(cosine_similarity(a, b), -1.0)

    def test_partial(self):
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([0.5, 0.5], dtype=np.float32)
        sim = cosine_similarity(a, b)
        expected = 0.5 / (1.0 * np.sqrt(0.5))
        self.assertAlmostEqual(sim, expected)

    def test_zero_vector(self):
        a = np.array([1.0, 0.0], dtype=np.float32)
        zero = np.array([0.0, 0.0], dtype=np.float32)
        self.assertAlmostEqual(cosine_similarity(a, zero), 0.0)
        self.assertAlmostEqual(cosine_similarity(zero, zero), 0.0)


if __name__ == "__main__":
    unittest.main()
