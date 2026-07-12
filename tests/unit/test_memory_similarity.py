"""Tests for memory.similarity — tokenize, jaccard_similarity, get_text_similarity."""

import unittest
from memory.similarity import tokenize, jaccard_similarity


class TestTokenize(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(tokenize("hello world"), ["hello", "world"])

    def test_punctuation_stripped(self):
        result = tokenize("hello, world!")
        self.assertEqual(result, ["hello", "world"])

    def test_empty(self):
        self.assertEqual(tokenize(""), [])


class TestJaccardSimilarity(unittest.TestCase):
    def test_identical(self):
        self.assertAlmostEqual(jaccard_similarity("hello world", "hello world"), 1.0)

    def test_partial(self):
        sim = jaccard_similarity("hello world", "hello there")
        self.assertAlmostEqual(sim, 1 / 3)

    def test_disjoint(self):
        self.assertAlmostEqual(jaccard_similarity("abc", "xyz"), 0.0)

    def test_empty_input(self):
        self.assertAlmostEqual(jaccard_similarity("", "hello"), 0.0)
        self.assertAlmostEqual(jaccard_similarity("hello", ""), 0.0)
        self.assertAlmostEqual(jaccard_similarity("", ""), 0.0)

    def test_case_insensitive(self):
        self.assertAlmostEqual(jaccard_similarity("Hello World", "hello world"), 1.0)


if __name__ == "__main__":
    unittest.main()
