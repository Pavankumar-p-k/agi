import os
import shutil
import tempfile
import unittest

from core.coding import CodingAI, CodingConstraints, CodingStatus, FileChange, ChangeType


class TestCodingAIContract(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        files = {
            "src/auth.py": "def login(user):\n    return True\n",
            "src/helpers.py": "def format_name(name):\n    return name.strip()\n",
            "src/tests/test_auth.py": "from src.auth import login\n\ndef test_login():\n    assert login('u')\n",
        }
        for path, content in files.items():
            full = os.path.join(self._tmp, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as handle:
                handle.write(content)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_capability_contract_has_boundaries(self):
        ai = CodingAI(self._tmp)
        contract = ai.capability_contract()
        self.assertIn("understand repositories", contract["can"])
        self.assertIn("replace the future Super-Brain", contract["cannot"])

    def test_execute_high_risk_requires_approval(self):
        ai = CodingAI(self._tmp)
        result = ai.execute(
            "Fix authentication bug",
            changes=[FileChange(ChangeType.MODIFY, "src/auth.py", "Investigate login")],
        )
        self.assertEqual(result.status, CodingStatus.PARTIAL)
        self.assertIn("status", result.to_dict())
        self.assertTrue(result.failures)

    def test_execute_returns_structured_unknown_without_implementer(self):
        ai = CodingAI(self._tmp)
        result = ai.execute(
            "Update helper",
            constraints=CodingConstraints(commands=[]),
            changes=[FileChange(ChangeType.MODIFY, "src/helpers.py", "Review helper")],
        )
        data = result.to_dict()
        self.assertEqual(data["status"], "unknown")
        self.assertIn("plan", data)
        self.assertIn("verification", data)
        self.assertIn("evidence", data)
