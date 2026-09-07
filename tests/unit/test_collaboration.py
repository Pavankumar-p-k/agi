"""Tests for Phase 11 — Multi-Agent Collaboration.

Covers CollaborationSession lifecycle, coordinator, consensus,
artifact review, and negotiation modules.
"""

import uuid
from unittest import TestCase

from core.collaboration.models import (
    ArtifactReview,
    ArtifactVersion,
    CollaborationSession,
    CollaborationStatus,
    ConsensusVote,
    ReviewDecision,
    ReviewRound,
    VoteValue,
)
from core.collaboration.coordinator import CollaborationCoordinator
from core.collaboration.consensus import ConsensusEngine
from core.collaboration.review import ArtifactReviewer
from core.collaboration.negotiation import NegotiationEngine


def _make_session() -> CollaborationSession:
    return CollaborationSession(
        session_id="col_test_001",
        goal="Build the payment feature",
        primary_agent_id="forge",
        reviewer_agent_ids=["cipher", "scribe"],
    )


def _make_version(agent_id: str = "forge", content: str = "def pay(): pass") -> ArtifactVersion:
    return ArtifactVersion(
        version_id=f"v_{uuid.uuid4().hex[:8]}",
        agent_id=agent_id,
        content=content,
        description="draft",
    )


def _make_review(decision: ReviewDecision, reviewer_id: str = "cipher",
                 issues: list[str] | None = None,
                 suggestions: list[str] | None = None) -> ArtifactReview:
    return ArtifactReview(
        review_id=f"rev_{uuid.uuid4().hex[:8]}",
        reviewer_id=reviewer_id,
        artifact_version_id="v_dummy",
        decision=decision,
        comments="Review comment",
        issues=issues or [],
        suggestions=suggestions or [],
        score=0.5,
    )


# ─── models.py ─────────────────────────────────────────────────────────────


class TestCollaborationModels(TestCase):
    """CollaborationSession, ArtifactVersion, ArtifactReview, ConsensusVote."""

    def test_01_session_create_with_defaults(self):
        s = _make_session()
        self.assertEqual(s.session_id, "col_test_001")
        self.assertEqual(s.goal, "Build the payment feature")
        self.assertEqual(s.primary_agent_id, "forge")
        self.assertEqual(s.reviewer_agent_ids, ["cipher", "scribe"])
        self.assertIs(s.status, CollaborationStatus.PENDING)
        self.assertEqual(s.review_rounds, [])
        self.assertIsNone(s.final_artifact)
        self.assertEqual(s.votes, [])
        self.assertEqual(s.max_review_rounds, 3)
        self.assertIsNone(s.created_at)
        self.assertIsNone(s.completed_at)
        self.assertEqual(s.metadata, {})

    def test_02_session_current_round(self):
        s = _make_session()
        self.assertEqual(s.current_round, 0)

        v = _make_version()
        r = ReviewRound(round_number=1, artifact_version=v)
        s.review_rounds.append(r)
        self.assertEqual(s.current_round, 1)

        s.review_rounds.append(ReviewRound(round_number=2, artifact_version=v))
        self.assertEqual(s.current_round, 2)

    def test_03_session_latest_version_and_review(self):
        s = _make_session()
        self.assertIsNone(s.latest_version)
        self.assertIsNone(s.latest_review)

        v1 = _make_version(content="version one")
        s.review_rounds.append(ReviewRound(round_number=1, artifact_version=v1))
        self.assertEqual(s.latest_version.content, "version one")
        self.assertIsNone(s.latest_review)

        rev = _make_review(ReviewDecision.APPROVED)
        s.review_rounds[-1].review = rev
        self.assertEqual(s.latest_review.decision, ReviewDecision.APPROVED)

        v2 = _make_version(content="version two")
        s.review_rounds.append(ReviewRound(round_number=2, artifact_version=v2))
        self.assertEqual(s.latest_version.content, "version two")
        self.assertIsNone(s.latest_review)

    def test_04_artifact_review_all_fields(self):
        r = ArtifactReview(
            review_id="rev_001",
            reviewer_id="cipher",
            artifact_version_id="v_abc123",
            decision=ReviewDecision.CHANGES_REQUESTED,
            comments="Fix the edge cases",
            issues=["Missing null check", "No error handling"],
            suggestions=["Add try/except", "Validate input"],
            score=0.3,
        )
        self.assertEqual(r.review_id, "rev_001")
        self.assertEqual(r.reviewer_id, "cipher")
        self.assertEqual(r.artifact_version_id, "v_abc123")
        self.assertIs(r.decision, ReviewDecision.CHANGES_REQUESTED)
        self.assertEqual(len(r.issues), 2)
        self.assertEqual(len(r.suggestions), 2)
        self.assertAlmostEqual(r.score, 0.3)

        d = r.to_dict()
        self.assertIn("review_id", d)
        self.assertIn("decision", d)
        self.assertEqual(d["decision"], "CHANGES_REQUESTED")

    def test_05_consensus_vote_values(self):
        v1 = ConsensusVote(voter_id="cipher", vote=VoteValue.APPROVE, rationale="Looks good")
        self.assertEqual(v1.voter_id, "cipher")
        self.assertIs(v1.vote, VoteValue.APPROVE)
        self.assertEqual(v1.rationale, "Looks good")

        v2 = ConsensusVote(voter_id="scribe", vote=VoteValue.REJECT)
        self.assertIs(v2.vote, VoteValue.REJECT)

        v3 = ConsensusVote(voter_id="sage", vote=VoteValue.ABSTAIN)
        self.assertIs(v3.vote, VoteValue.ABSTAIN)


# ─── coordinator.py ────────────────────────────────────────────────────────


class TestCollaborationCoordinator(TestCase):
    """CollaborationCoordinator — session lifecycle orchestration."""

    def setUp(self):
        self._coord = CollaborationCoordinator()

    @staticmethod
    def _always_approve(agent_id: str, goal: str) -> str:
        return f"def {agent_id}_{goal.replace(' ', '_')}(): pass"

    @staticmethod
    def _review_approve(reviewer_id: str, artifact: str, goal: str) -> ArtifactReview:
        return _make_review(ReviewDecision.APPROVED, reviewer_id=reviewer_id)

    @staticmethod
    def _review_changes_requested(reviewer_id: str, artifact: str, goal: str) -> ArtifactReview:
        return _make_review(ReviewDecision.CHANGES_REQUESTED, reviewer_id=reviewer_id,
                            issues=["Missing validation"], suggestions=["Add input check"])

    @staticmethod
    def _review_reject(reviewer_id: str, artifact: str, goal: str) -> ArtifactReview:
        return _make_review(ReviewDecision.REJECTED, reviewer_id=reviewer_id,
                            issues=["Fundamental flaw"])

    def test_06_create_session(self):
        s = self._coord.create_session(
            goal="Implement auth",
            primary_agent="forge",
            reviewers=["cipher", "scribe"],
            max_rounds=5,
        )
        self.assertIsNotNone(s.session_id)
        self.assertTrue(s.session_id.startswith("col_"))
        self.assertEqual(s.goal, "Implement auth")
        self.assertEqual(s.primary_agent_id, "forge")
        self.assertEqual(s.reviewer_agent_ids, ["cipher", "scribe"])
        self.assertEqual(s.max_review_rounds, 5)
        self.assertIs(s.status, CollaborationStatus.PENDING)
        self.assertIsNotNone(s.created_at)

    def test_07_get_session(self):
        self.assertIsNone(self._coord.get_session("col_nonexistent"))

        s = self._coord.create_session("Test", "forge")
        retrieved = self._coord.get_session(s.session_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.session_id, s.session_id)

    def test_08_run_full_session_happy_path(self):
        s = self._coord.create_session("Build payment", "forge", ["cipher"])
        result = self._coord.run_full_session(
            s.session_id,
            execute_fn=self._always_approve,
            review_fn=self._review_approve,
        )
        self.assertIs(result.status, CollaborationStatus.COMPLETED)
        self.assertIsNotNone(result.final_artifact)
        self.assertIn("forge", result.final_artifact)
        self.assertIsNotNone(result.completed_at)
        self.assertEqual(result.current_round, 1)

    def test_09_run_full_session_revision_path(self):
        """Producer revises after changes_requested, then approved."""
        call_count = [0]

        def _produce_revise(agent_id: str, prompt: str) -> str:
            call_count[0] += 1
            if call_count[0] == 1:
                return "first draft with issues"
            return "revised clean version"

        def _review_then_approve(reviewer_id: str, artifact: str, goal: str) -> ArtifactReview:
            if "issues" in artifact:
                return _make_review(ReviewDecision.CHANGES_REQUESTED, reviewer_id=reviewer_id,
                                    issues=["Fix quality"], suggestions=["Polish"])
            return _make_review(ReviewDecision.APPROVED, reviewer_id=reviewer_id)

        s = self._coord.create_session("Polish feature", "forge", ["cipher"])
        result = self._coord.run_full_session(
            s.session_id,
            execute_fn=_produce_revise,
            review_fn=_review_then_approve,
        )
        self.assertIs(result.status, CollaborationStatus.COMPLETED)
        self.assertEqual(result.current_round, 2)
        self.assertEqual(result.final_artifact, "revised clean version")

    def test_10_run_full_session_escalation_path(self):
        """Reviewers keep rejecting until max_rounds → ESCALATED."""
        s = self._coord.create_session("Tough feature", "forge", ["cipher"], max_rounds=2)

        def _always_produce(agent_id: str, goal: str) -> str:
            return "same draft"

        def _always_reject(reviewer_id: str, artifact: str, goal: str) -> ArtifactReview:
            return _make_review(ReviewDecision.REJECTED, reviewer_id=reviewer_id,
                                issues=["Still wrong"])

        result = self._coord.run_full_session(
            s.session_id,
            execute_fn=_always_produce,
            review_fn=_always_reject,
        )
        self.assertIs(result.status, CollaborationStatus.ESCALATED)
        self.assertEqual(result.current_round, 1)
        self.assertIsNotNone(result.final_artifact)

    def test_11a_coordinator_uses_consensus_engine(self):
        """Coordinator delegates to ConsensusEngine (not _aggregate_reviews)."""
        self.assertTrue(hasattr(self._coord, "consensus"))
        self.assertIsInstance(self._coord.consensus, ConsensusEngine)

    def test_11b_coordinator_uses_negotiation_engine(self):
        """Coordinator delegates to NegotiationEngine."""
        self.assertTrue(hasattr(self._coord, "negotiation"))
        self.assertIsInstance(self._coord.negotiation, NegotiationEngine)

    def test_11c_supermajority_via_coordinator(self):
        """3 approves + 1 reject = supermajority overrides → CHANGES_REQUESTED."""
        coord = CollaborationCoordinator()

        rev_approve = _make_review(ReviewDecision.APPROVED)
        rev_reject = _make_review(ReviewDecision.REJECTED)

        decision = coord.consensus.resolve(
            [rev_approve, rev_approve, rev_approve, rev_reject]
        )
        self.assertIs(decision, ReviewDecision.CHANGES_REQUESTED)

    def test_11d_reject_no_supermajority_via_coordinator(self):
        """1 reject + 2 approve without supermajority → REJECTED via coordinator."""
        coord = CollaborationCoordinator()

        rev_approve = _make_review(ReviewDecision.APPROVED)
        rev_reject = _make_review(ReviewDecision.REJECTED)

        decision = coord.consensus.resolve(
            [rev_approve, rev_approve, rev_reject]
        )
        self.assertIs(decision, ReviewDecision.REJECTED)

    def test_11e_negotiation_triggers_on_disagreement(self):
        """Disagreement triggers negotiation before consensus."""
        coord = CollaborationCoordinator()

        s = coord.create_session("Disagree", "forge", ["cipher"])
        s.status = CollaborationStatus.IN_REVIEW

        # Disagreeing reviews — should trigger negotiation
        reviews = [
            _make_review(ReviewDecision.CHANGES_REQUESTED, issues=["Fix this"],
                         suggestions=["Improve X"]),
        ]
        result = coord.negotiation.negotiate(s, reviews)
        self.assertIs(result.status, CollaborationStatus.IN_NEGOTIATION)


# ─── consensus.py ──────────────────────────────────────────────────────────


class TestConsensusEngine(TestCase):
    """ConsensusEngine — canonical ArtifactReview → ConsensusVote → Decision."""

    def setUp(self):
        self._engine = ConsensusEngine()

    def _review(self, decision: ReviewDecision) -> ArtifactReview:
        return _make_review(decision)

    def test_12_all_approve(self):
        reviews = [self._review(ReviewDecision.APPROVED) for _ in range(3)]
        result = self._engine.resolve(reviews)
        self.assertIs(result, ReviewDecision.APPROVED)

    def test_13_single_reject_no_supermajority(self):
        reviews = [
            self._review(ReviewDecision.APPROVED),
            self._review(ReviewDecision.APPROVED),
            self._review(ReviewDecision.REJECTED),
        ]
        result = self._engine.resolve(reviews)
        self.assertIs(result, ReviewDecision.REJECTED)

    def test_14_supermajority_overrides_single_reject(self):
        reviews = [
            self._review(ReviewDecision.APPROVED),
            self._review(ReviewDecision.APPROVED),
            self._review(ReviewDecision.APPROVED),
            self._review(ReviewDecision.REJECTED),
        ]
        result = self._engine.resolve(reviews)
        self.assertIs(result, ReviewDecision.CHANGES_REQUESTED)

    def test_15_tiebreaker_decides(self):
        reviews = [
            self._review(ReviewDecision.APPROVED),
            self._review(ReviewDecision.CHANGES_REQUESTED),
        ]

        result = self._engine.resolve(reviews, tiebreaker_vote=VoteValue.APPROVE)
        self.assertIs(result, ReviewDecision.APPROVED)

        result = self._engine.resolve(reviews, tiebreaker_vote=VoteValue.REJECT)
        self.assertIs(result, ReviewDecision.REJECTED)

        result = self._engine.resolve(reviews, tiebreaker_vote=VoteValue.ABSTAIN)
        self.assertIs(result, ReviewDecision.CHANGES_REQUESTED)

    def test_16_majority_changes_requested(self):
        reviews = [
            self._review(ReviewDecision.CHANGES_REQUESTED),
            self._review(ReviewDecision.CHANGES_REQUESTED),
            self._review(ReviewDecision.APPROVED),
        ]
        result = self._engine.resolve(reviews)
        self.assertIs(result, ReviewDecision.CHANGES_REQUESTED)

    def test_16b_reviews_to_votes_maps_correctly(self):
        reviews = [
            _make_review(ReviewDecision.APPROVED, reviewer_id="a"),
            _make_review(ReviewDecision.CHANGES_REQUESTED, reviewer_id="b"),
            _make_review(ReviewDecision.REJECTED, reviewer_id="c"),
        ]
        votes = self._engine.reviews_to_votes(reviews)
        self.assertEqual(len(votes), 3)
        self.assertEqual(votes[0].vote, VoteValue.APPROVE)
        self.assertEqual(votes[1].vote, VoteValue.ABSTAIN)
        self.assertEqual(votes[2].vote, VoteValue.REJECT)
        self.assertEqual(votes[0].voter_id, "a")
        self.assertEqual(votes[1].voter_id, "b")
        self.assertEqual(votes[2].voter_id, "c")

    def test_16c_empty_reviews_approved(self):
        result = self._engine.resolve([])
        self.assertIs(result, ReviewDecision.APPROVED)

    def test_16d_needs_tiebreaker_true_when_tied(self):
        votes = [
            ConsensusVote(voter_id="a", vote=VoteValue.APPROVE),
            ConsensusVote(voter_id="b", vote=VoteValue.REJECT),
        ]
        self.assertTrue(self._engine.needs_tiebreaker(votes))

    def test_16e_needs_tiebreaker_false_when_unanimous(self):
        votes = [
            ConsensusVote(voter_id="a", vote=VoteValue.APPROVE),
            ConsensusVote(voter_id="b", vote=VoteValue.APPROVE),
        ]
        self.assertFalse(self._engine.needs_tiebreaker(votes))


# ─── review.py ─────────────────────────────────────────────────────────────


class TestArtifactReviewer(TestCase):
    """ArtifactReviewer — deterministic pattern-based review."""

    def setUp(self):
        self._reviewer = ArtifactReviewer(reviewer_id="cipher")

    def test_17_clean_artifact_approved(self):
        content = """def calculate_total(items):
    result = sum(item.price for item in items)
    return result
"""
        review = self._reviewer.review_artifact(content, "Calculate total price")
        self.assertIs(review.decision, ReviewDecision.APPROVED)
        self.assertAlmostEqual(review.score, 1.0)
        self.assertEqual(len(review.issues), 0)

    def test_18_artifact_with_todos_detects_issues(self):
        content = """def process():
    # TODO: implement error handling
    # FIXME: this is a hack
    pass
"""
        review = self._reviewer.review_artifact(content, "Process data")
        self.assertIs(review.decision, ReviewDecision.CHANGES_REQUESTED)
        todo_issues = [i for i in review.issues if "placeholder" in i.lower()]
        self.assertGreaterEqual(len(todo_issues), 1)
        self.assertLessEqual(len(review.issues), 2)

    def test_19_security_pattern_detected(self):
        content = """def connect():
    password = "super_secret_123"
    token = "abc123def"
    return connect_db(password, token)
"""
        review = self._reviewer.review_artifact(content, "Database connection")
        security_issues = [i for i in review.issues if "SECURITY" in i]
        self.assertGreaterEqual(len(security_issues), 1)
        self.assertIs(review.decision, ReviewDecision.CHANGES_REQUESTED)

    def test_20_very_short_artifact_flagged(self):
        content = "short"
        review = self._reviewer.review_artifact(content, "Write documentation")
        length_issues = [i for i in review.issues if "short" in i.lower()]
        self.assertGreaterEqual(len(length_issues), 1)
        self.assertIs(review.decision, ReviewDecision.CHANGES_REQUESTED)


# ─── negotiation.py ────────────────────────────────────────────────────────


class TestNegotiationEngine(TestCase):
    """NegotiationEngine — conflict resolution / compromise."""

    def setUp(self):
        self._engine = NegotiationEngine()

    def test_21_negotiate_all_approves_returns_to_review(self):
        s = _make_session()
        s.status = CollaborationStatus.IN_REVIEW
        reviews = [_make_review(ReviewDecision.APPROVED, suggestions=["Nice work"])]
        result = self._engine.negotiate(s, reviews)
        self.assertIs(result.status, CollaborationStatus.IN_REVIEW)

    def test_22_negotiate_rejects_outweigh_approves_escalates(self):
        s = _make_session()
        s.status = CollaborationStatus.IN_REVIEW
        reviews = [
            _make_review(ReviewDecision.REJECTED, reviewer_id="cipher",
                         issues=["Fundamental flaw"]),
            _make_review(ReviewDecision.REJECTED, reviewer_id="scribe",
                         issues=["Also broken"]),
            _make_review(ReviewDecision.APPROVED, reviewer_id="sage"),
        ]
        result = self._engine.negotiate(s, reviews)
        self.assertIs(result.status, CollaborationStatus.ESCALATED)

    def test_23_suggest_compromise_priority_issues(self):
        reviews = [
            _make_review(ReviewDecision.CHANGES_REQUESTED, reviewer_id="cipher",
                         issues=["Missing validation", "No error handling"],
                         suggestions=["Add input check", "Add try/except"]),
            _make_review(ReviewDecision.CHANGES_REQUESTED, reviewer_id="scribe",
                         issues=["Missing validation", "Poor naming"],
                         suggestions=["Rename variables"]),
        ]
        result = self._engine.suggest_compromise(_make_session(), reviews)
        self.assertEqual(result["action"], "revise")
        self.assertIn("Missing validation", result["priority_issues"])
        self.assertEqual(len(result["priority_issues"]), 1)
        self.assertIsInstance(result["agreed_points"], list)
        self.assertIsInstance(result["disputed_points"], list)

    def test_24_negotiation_enforces_max_rounds(self):
        s = _make_session()
        s.status = CollaborationStatus.IN_REVIEW
        reviews = [
            _make_review(ReviewDecision.CHANGES_REQUESTED, reviewer_id="cipher",
                         suggestions=["Fix it"]),
        ]
        result = self._engine.negotiate(s, reviews, negotiation_round=5)
        self.assertIs(result.status, CollaborationStatus.ESCALATED)

    def test_25_negotiation_disagreement_enters_negotiation(self):
        s = _make_session()
        s.status = CollaborationStatus.IN_REVIEW
        reviews = [
            _make_review(ReviewDecision.CHANGES_REQUESTED, issues=["Fix X"]),
        ]
        result = self._engine.negotiate(s, reviews)
        self.assertIs(result.status, CollaborationStatus.IN_NEGOTIATION)

    def test_26_disagreement_triggers_negotiation_before_consensus(self):
        """End-to-end: disagreement → negotiate → consensus pipeline."""
        coord = CollaborationCoordinator()
        s = coord.create_session("E2E test", "forge", ["cipher", "scribe"], max_rounds=2)

        produce_call_count = [0]

        def _produce(agent_id: str, goal: str) -> str:
            produce_call_count[0] += 1
            if produce_call_count[0] == 1:
                return "initial version"
            return "revised version"

        def _mixed_review(reviewer_id: str, artifact: str, goal: str) -> ArtifactReview:
            if reviewer_id == "cipher":
                return _make_review(ReviewDecision.APPROVED, reviewer_id="cipher")
            if "revised" in artifact.lower():
                return _make_review(ReviewDecision.APPROVED, reviewer_id="scribe")
            return _make_review(ReviewDecision.CHANGES_REQUESTED, reviewer_id="scribe",
                                issues=["Needs polish"], suggestions=["Refine"])

        result = coord.run_full_session(s.session_id, _produce, _mixed_review)
        # Should complete via revision path (not escalated)
        self.assertIs(result.status, CollaborationStatus.COMPLETED)
        self.assertEqual(result.current_round, 2)
