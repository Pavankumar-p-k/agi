"""
tests/test_all.py — JARVIS Social AI — Full Test Suite
=======================================================
Tests:
 - Special friend detection
 - Cooldown enforcement (no double-text)
 - Offline fallback
 - Intervention triggers
 - Experiment revert logic
 - Shadow learning / trait update
 - Memory cleanup
 - Trait clamping
 - Hard-locked traits
 - DB integrity
"""
import asyncio, os, time, pytest, tempfile

from services.jarvis_social.db import schema
from services.jarvis_social.db.schema import connect, clamp, init_db, set_setting, get_setting
from services.jarvis_social.friends.registry import FriendRegistry, SPECIAL_FRIENDS
from services.jarvis_social.reply.auto_reply import AutoReplyEngine, OFFLINE_FALLBACK
from services.jarvis_social.brain.learning import ShadowLearner
from services.jarvis_social.experiments.engine import ExperimentEngine, InterventionEngine
from services.jarvis_social.memory.cleanup import MemoryCleanup


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    db = str(tmp_path / "test.db")
    schema.DB_PATH = db
    init_db(db)
    return db


@pytest.fixture
def registry(tmp_db):
    return FriendRegistry(tmp_db)


@pytest.fixture
def engine(tmp_db):
    return ExperimentEngine(tmp_db)


@pytest.fixture
def intervention_engine(tmp_db):
    return InterventionEngine(tmp_db)


# ══════════════════════════════════════════════════
#  1. DB SCHEMA TESTS
# ══════════════════════════════════════════════════

class TestSchema:

    def test_init_creates_tables(self, tmp_db):
        con = connect(tmp_db)
        tables = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        names = {r[0] for r in tables}
        assert "personality_vectors" in names
        assert "friends" in names
        assert "short_term_messages" in names
        assert "metadata_logs" in names
        assert "experiment_history" in names
        assert "intervention_logs" in names
        assert "memory_tokens" in names
        con.close()

    def test_clamp_low(self):
        assert clamp(-0.5) == 0.0

    def test_clamp_high(self):
        assert clamp(1.5) == 1.0

    def test_clamp_middle(self):
        assert clamp(0.7) == pytest.approx(0.7)

    def test_clamp_exact_bounds(self):
        assert clamp(0.0) == 0.0
        assert clamp(1.0) == 1.0

    def test_settings_get_set(self, tmp_db):
        set_setting("test_key", "hello", tmp_db)
        assert get_setting("test_key", tmp_db) == "hello"

    def test_global_traits_singleton(self, tmp_db):
        con = connect(tmp_db)
        rows = con.execute("SELECT COUNT(*) FROM global_jarvis_traits").fetchone()[0]
        con.close()
        assert rows == 1


# ══════════════════════════════════════════════════
#  2. FRIEND REGISTRY TESTS
# ══════════════════════════════════════════════════

class TestFriendRegistry:

    def _add_friend(self, reg, name="TestFriend", phone="+91999", insta="testuser"):
        reg._upsert_friend("testfriend", name, phone=phone, instagram_id=insta)
        reg._upsert_vector("testfriend", {"humor":0.5,"caring":0.5,"formality":0.4,
                                           "emoji":0.3,"energy":0.5,"directness":0.5})
        return reg.get_profile("testfriend")

    def test_create_and_retrieve_friend(self, registry):
        p = self._add_friend(registry)
        assert p is not None
        assert p.display_name == "TestFriend"

    def test_phone_lookup(self, registry):
        self._add_friend(registry, phone="+91999")
        found = registry._find_by_identifier("+91999")
        assert found is not None
        assert found.display_name == "TestFriend"

    def test_instagram_lookup(self, registry):
        self._add_friend(registry, insta="testuser")
        found = registry._find_by_identifier("testuser")
        assert found is not None

    def test_nickname_fuzzy_match(self, registry, tmp_db):
        registry._upsert_friend("nf", "Nick Friend", nickname="buddy")
        registry._upsert_vector("nf", {})
        # "budy" is close to "buddy"
        found = registry._find_by_identifier("budy")
        assert found is not None

    def test_special_mode_toggle(self, registry):
        self._add_friend(registry)
        registry.set_special_mode("testfriend", True)
        p = registry.get_profile("testfriend")
        assert p.special_mode is True
        registry.set_special_mode("testfriend", False)
        p = registry.get_profile("testfriend")
        assert p.special_mode is False

    def test_cooldown_set_and_check(self, registry):
        self._add_friend(registry)
        registry.set_cooldown("testfriend", special=False)
        assert registry.is_in_cooldown("testfriend") is True

    def test_cooldown_cleared(self, registry):
        self._add_friend(registry)
        registry.set_cooldown("testfriend")
        registry.clear_cooldown("testfriend")
        assert registry.is_in_cooldown("testfriend") is False

    def test_cooldown_not_blocking_fresh_friend(self, registry):
        self._add_friend(registry)
        assert registry.is_in_cooldown("testfriend") is False

    def test_locked_trait_raises(self, registry):
        self._add_friend(registry)
        with pytest.raises(ValueError):
            registry.update_trait("testfriend", "manipulation", 0.5)

    def test_locked_trait_aggression(self, registry):
        self._add_friend(registry)
        with pytest.raises(ValueError):
            registry.update_trait("testfriend", "aggression", 0.1)

    def test_trait_clamped_on_update(self, registry):
        self._add_friend(registry)
        registry.update_trait("testfriend", "humor", 1.5)
        traits = registry.get_traits("testfriend")
        assert traits["humor"] <= 1.0

    def test_awaiting_reply_set(self, registry):
        self._add_friend(registry)
        registry.set_awaiting_reply("testfriend", True)
        p = registry.get_profile("testfriend")
        assert p.awaiting_reply is True

    def test_awaiting_reply_cleared(self, registry):
        self._add_friend(registry)
        registry.set_awaiting_reply("testfriend", True)
        registry.mark_reply_received("testfriend")
        p = registry.get_profile("testfriend")
        assert p.awaiting_reply is False

    def test_can_initiate_requires_no_cooldown(self, registry):
        self._add_friend(registry)
        # No cooldown, no awaiting reply, engagement = 0.5 (above threshold)
        p = registry.get_profile("testfriend")
        # Engagement 0.5 > 0.35 threshold
        assert p.can_initiate is True

    def test_can_initiate_blocked_during_cooldown(self, registry):
        self._add_friend(registry)
        registry.set_cooldown("testfriend")
        p = registry.get_profile("testfriend")
        assert p.can_initiate is False

    def test_can_initiate_blocked_awaiting_reply(self, registry):
        self._add_friend(registry)
        registry.set_awaiting_reply("testfriend", True)
        p = registry.get_profile("testfriend")
        assert p.can_initiate is False


# ══════════════════════════════════════════════════
#  3. AUTO REPLY TESTS
# ══════════════════════════════════════════════════

class TestAutoReply:

    sent_messages = []

    @pytest.fixture
    def reply_engine(self, tmp_db):
        self.sent_messages = []
        async def mock_send(fid, text):
            self.sent_messages.append((fid, text))
            return True
        engine = AutoReplyEngine(db_path=tmp_db, send_fn=mock_send)
        # Register a test friend
        reg = FriendRegistry(tmp_db)
        reg._upsert_friend("friend1", "Friend One", phone="+111")
        reg._upsert_vector("friend1", {"humor":0.5,"caring":0.5,"formality":0.4,
                                        "emoji":0.3,"energy":0.5,"directness":0.5})
        return engine

    def test_offline_fallback_sent(self, reply_engine, tmp_db):
        set_setting("laptop_status", "offline", tmp_db)
        result = asyncio.run(reply_engine.handle_incoming("friend1", "hey!"))
        assert result.sent is True
        assert result.reason == "offline"
        assert OFFLINE_FALLBACK in result.text

    def test_system_pause_blocks_reply(self, reply_engine, tmp_db):
        set_setting("system_paused", "true", tmp_db)
        result = asyncio.run(reply_engine.handle_incoming("friend1", "hey!"))
        assert result.sent is False
        assert result.reason == "system_paused"

    def test_auto_reply_disabled_blocks(self, reply_engine, tmp_db):
        set_setting("auto_reply_enabled", "false", tmp_db)
        result = asyncio.run(reply_engine.handle_incoming("friend1", "hey!"))
        assert result.sent is False

    def test_double_text_prevention(self, reply_engine, tmp_db):
        """Two messages within 30s should block second reply."""
        reply_engine._last_sent["friend1"] = time.time()  # simulate just sent
        result = asyncio.run(reply_engine.handle_incoming("friend1", "hey again!"))
        assert result.reason == "double_text"
        assert result.sent is False

    def test_safety_filter_softens_conflict(self, reply_engine, tmp_db):
        aggressive_reply = "you're wrong and stupid"
        filtered = reply_engine._safety_filter(aggressive_reply, "i'm angry at you")
        assert "stupid" not in filtered.lower()

    def test_message_stored_after_incoming(self, reply_engine, tmp_db):
        asyncio.run(reply_engine.handle_incoming("friend1", "test message"))
        con = connect(tmp_db)
        count = con.execute(
            "SELECT COUNT(*) FROM short_term_messages WHERE friend_id='friend1'"
        ).fetchone()[0]
        con.close()
        assert count >= 1


# ══════════════════════════════════════════════════
#  4. SHADOW LEARNING TESTS
# ══════════════════════════════════════════════════

class TestShadowLearner:

    @pytest.fixture
    def learner_with_friend(self, tmp_db):
        reg = FriendRegistry(tmp_db)
        reg._upsert_friend("learner1", "Learner")
        reg._upsert_vector("learner1", {"humor":0.5,"caring":0.5,"formality":0.5,
                                         "emoji":0.3,"energy":0.5,"directness":0.5})
        return ShadowLearner(tmp_db)

    def test_extract_tone_emoji_heavy(self, learner_with_friend):
        obs = learner_with_friend._extract_tone("hey!!! 😂😂😂 so funny haha")
        assert obs["emoji"] > 0.3

    def test_extract_tone_humor_detected(self, learner_with_friend):
        obs = learner_with_friend._extract_tone("haha lol that's so funny lmao 😂")
        assert obs["humor"] > 0.0

    def test_extract_tone_informal_low_formality(self, learner_with_friend):
        obs = learner_with_friend._extract_tone("ya gonna nah dunno tbh rn")
        assert obs["formality"] < 0.5

    def test_max_shift_capped(self, learner_with_friend):
        """Single session shift should never exceed 0.05 per trait."""
        from brain.learning import MAX_SHIFT_PER_SESSION
        learner_with_friend.reset_session("learner1")
        suggestions = learner_with_friend.observe_manual_message(
            "learner1", "haha 😂😂😂 lol lmao funny joke jk kidding 😂😂" * 5
        )
        for trait, new_val in suggestions.items():
            reg = FriendRegistry(learner_with_friend._db)
            old_val = reg.get_traits("learner1").get(trait, 0.5)
            shift = abs(new_val - old_val)
            assert shift <= MAX_SHIFT_PER_SESSION + 0.001  # float tolerance

    def test_locked_traits_not_in_suggestions(self, learner_with_friend):
        suggestions = learner_with_friend.observe_manual_message(
            "learner1", "you are manipulative and aggressive"
        )
        for locked in ["manipulation","aggression","dependency"]:
            assert locked not in suggestions


# ══════════════════════════════════════════════════
#  5. EXPERIMENT ENGINE TESTS
# ══════════════════════════════════════════════════

class TestExperimentEngine:

    @pytest.fixture
    def exp_with_friend(self, tmp_db, engine):
        reg = FriendRegistry(tmp_db)
        reg._upsert_friend("exp1", "Exp Friend")
        reg._upsert_vector("exp1", {"humor":0.5,"caring":0.5,"formality":0.5,
                                     "emoji":0.3,"energy":0.5,"directness":0.5,
                                     "engagement_score":0.5})
        return engine

    def test_start_experiment(self, exp_with_friend):
        exp = exp_with_friend.start_experiment("exp1")
        assert exp is not None
        assert exp.result == "pending"

    def test_no_duplicate_experiment(self, exp_with_friend):
        exp_with_friend.start_experiment("exp1")
        exp2 = exp_with_friend.start_experiment("exp1")
        assert exp2 is None

    def test_test_value_within_shift(self, exp_with_friend):
        exp = exp_with_friend.start_experiment("exp1")
        assert abs(exp.test_value - exp.original_value) <= 0.05 + 0.001

    def test_test_value_clamped(self, exp_with_friend):
        # Force a trait to 1.0 and shift up — should stay ≤ 1.0
        reg = FriendRegistry(exp_with_friend._db)
        reg.update_trait("exp1", "humor", 1.0)
        exp = exp_with_friend.start_experiment("exp1", trait="humor")
        if exp:
            assert exp.test_value <= 1.0

    def test_locked_trait_not_selected(self, exp_with_friend):
        for _ in range(20):
            exp = exp_with_friend.start_experiment("exp1")
            if exp:
                assert exp.trait_name not in {"aggression","manipulation","dependency"}
                # Reset to allow another
                con = connect(exp_with_friend._db)
                con.execute("DELETE FROM experiment_history WHERE friend_id='exp1'")
                con.commit()
                con.close()

    def test_experiment_revert_on_low_engagement(self, tmp_db, exp_with_friend):
        """Simulate low engagement after experiment — should revert."""
        reg = FriendRegistry(tmp_db)
        original_humor = float(reg.get_traits("exp1").get("humor", 0.5))
        exp = exp_with_friend.start_experiment("exp1", trait="humor")
        if not exp:
            return
        # Simulate 20 ticks with low engagement (no metadata = default 0.5, but we set low)
        con = connect(tmp_db)
        # Insert low engagement metadata
        for i in range(5):
            con.execute(
                "INSERT INTO metadata_logs (friend_id,sentiment,conflict_flag,engagement,timestamp) "
                "VALUES ('exp1',0.1,1,0.1,?)", (time.time() - i*100,))
        con.commit()
        con.close()
        for _ in range(20):
            result = exp_with_friend.tick("exp1")
            if result:
                # Should have reverted since engagement dropped
                traits = reg.get_traits("exp1")
                if result == "reverted":
                    assert abs(float(traits.get("humor",0)) - original_humor) < 0.01
                break


# ══════════════════════════════════════════════════
#  6. INTERVENTION ENGINE TESTS
# ══════════════════════════════════════════════════

class TestInterventionEngine:

    @pytest.fixture
    def iv_with_friend(self, tmp_db, intervention_engine):
        reg = FriendRegistry(tmp_db)
        reg._upsert_friend("iv1", "IV Friend")
        reg._upsert_vector("iv1", {"humor":0.5,"caring":0.5,"formality":0.5,
                                    "emoji":0.3,"energy":0.5,"directness":0.5})
        return intervention_engine

    def _insert_metrics(self, db, friend_id, sentiment, conflict, engagement, count=5):
        con = connect(db)
        for i in range(count):
            con.execute(
                "INSERT INTO metadata_logs (friend_id,sentiment,conflict_flag,engagement,timestamp) "
                "VALUES (?,?,?,?,?)",
                (friend_id, sentiment, conflict, engagement, time.time() - i*3600)
            )
        con.commit()
        con.close()

    def test_low_engagement_triggers(self, iv_with_friend, tmp_db):
        self._insert_metrics(tmp_db, "iv1", 0.5, 0, 0.1)
        iv = iv_with_friend.check("iv1")
        assert iv is not None
        assert iv.trigger_reason == "engagement_drop"

    def test_conflict_spike_triggers(self, iv_with_friend, tmp_db):
        self._insert_metrics(tmp_db, "iv1", 0.2, 1, 0.5)  # conflict_flag=1
        iv = iv_with_friend.check("iv1")
        assert iv is not None

    def test_high_severity_suggests_manual(self, iv_with_friend, tmp_db):
        # Extremely low engagement → HIGH
        self._insert_metrics(tmp_db, "iv1", 0.1, 1, 0.05, count=10)
        iv = iv_with_friend.check("iv1")
        if iv and iv.severity == "HIGH":
            assert iv.manual_suggested is True

    def test_no_intervention_on_healthy_metrics(self, iv_with_friend, tmp_db):
        self._insert_metrics(tmp_db, "iv1", 0.8, 0, 0.8)
        iv = iv_with_friend.check("iv1")
        assert iv is None

    def test_intervention_logged(self, iv_with_friend, tmp_db):
        self._insert_metrics(tmp_db, "iv1", 0.1, 1, 0.1)
        iv_with_friend.check("iv1")
        logs = iv_with_friend.get_logs("iv1")
        assert len(logs) >= 1

    def test_trait_shift_clamped(self, iv_with_friend, tmp_db):
        reg = FriendRegistry(tmp_db)
        reg.update_trait("iv1", "energy", 0.99)
        self._insert_metrics(tmp_db, "iv1", 0.1, 0, 0.1)
        iv_with_friend.check("iv1")
        traits = reg.get_traits("iv1")
        assert float(traits.get("energy", 0)) <= 1.0


# ══════════════════════════════════════════════════
#  7. MEMORY CLEANUP TESTS
# ══════════════════════════════════════════════════

class TestMemoryCleanup:

    @pytest.fixture
    def cleanup(self, tmp_db):
        reg = FriendRegistry(tmp_db)
        reg._upsert_friend("mem1", "Mem Friend")
        con = connect(tmp_db)
        # Insert expired message
        con.execute(
            "INSERT INTO short_term_messages (friend_id,role,content,expires_at) "
            "VALUES ('mem1','user','call me buddy okay?', ?)",
            (time.time() - 1,)  # already expired
        )
        con.commit()
        con.close()
        return MemoryCleanup(tmp_db)

    def test_expired_messages_deleted(self, cleanup, tmp_db):
        cleanup.run_daily_cleanup()
        con = connect(tmp_db)
        count = con.execute(
            "SELECT COUNT(*) FROM short_term_messages WHERE friend_id='mem1'"
        ).fetchone()[0]
        con.close()
        assert count == 0

    def test_nickname_token_extracted(self, cleanup, tmp_db):
        cleanup.run_daily_cleanup()
        tokens = cleanup.get_tokens("mem1")
        nicknames = [t for t in tokens if t["token_type"] == "nickname"]
        assert any("buddy" in t["token_value"] for t in nicknames)

    def test_cleanup_stats_returned(self, cleanup):
        result = cleanup.run_daily_cleanup()
        assert "messages_deleted" in result
        assert "tokens_extracted" in result

    def test_live_messages_not_deleted(self, cleanup, tmp_db):
        con = connect(tmp_db)
        future_expire = time.time() + 86400 * 10
        con.execute(
            "INSERT INTO short_term_messages (friend_id,role,content,expires_at) "
            "VALUES ('mem1','user','still fresh',?)",
            (future_expire,)
        )
        con.commit()
        con.close()
        cleanup.run_daily_cleanup()
        con = connect(tmp_db)
        count = con.execute(
            "SELECT COUNT(*) FROM short_term_messages WHERE content='still fresh'"
        ).fetchone()[0]
        con.close()
        assert count == 1


# ══════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
