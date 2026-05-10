"""
friends/registry.py — Friend Classification + Special Friend Config
===================================================================
- Classifies friends as NORMAL or SPECIAL
- Auto-matches by phone, instagram_id, or nickname
- Manages personality vectors per friend
- Cooldown enforcement
"""
from __future__ import annotations
import sqlite3, time, difflib, json
from dataclasses import dataclass, field, asdict
from typing import Optional
from db.schema import connect, clamp, DB_PATH

# ══════════════════════════════════════════════════
#  SPECIAL FRIENDS CONFIG
#  Fill in your friends' details here.
# ══════════════════════════════════════════════════

SPECIAL_FRIENDS = [
    {
        "name":         "REPLACE_NAME",
        "phone":        "REPLACE_PHONE",
        "instagram_id": "REPLACE_ID",
        "nickname":     "REPLACE_NICK",
        "platform":     "whatsapp",
        "base_traits": {
            "humor":    0.7,
            "caring":   0.85,
            "emoji":    0.75,
            "energy":   0.7,
            "formality": 0.3,
            "directness": 0.6,
        }
    },
    # Add more special friends here:
    # {
    #     "name": "Friend2",
    #     "phone": "+91...",
    #     "instagram_id": "username",
    #     "nickname": "nick",
    #     "platform": "instagram",
    #     "base_traits": { "humor": 0.8, "caring": 0.9, ... }
    # },
]

# Cooldown durations
NORMAL_COOLDOWN_S  = 86400   # 24 hours
SPECIAL_COOLDOWN_S = 28800   # 8 hours

# Engagement threshold to allow initiation
MIN_ENGAGEMENT_FOR_INITIATION = 0.35

# Default personality for new normal friends
DEFAULT_NORMAL_TRAITS = {
    "humor": 0.4, "caring": 0.5, "formality": 0.5,
    "emoji": 0.3, "energy": 0.4, "directness": 0.5,
    "engagement_score": 0.5,
}


@dataclass
class FriendProfile:
    friend_id:    str
    display_name: str
    phone:        str = ""
    instagram_id: str = ""
    nickname:     str = ""
    platform:     str = "whatsapp"
    special_mode: bool = False
    traits:       dict = field(default_factory=dict)
    cooldown_until: float = 0.0
    engagement_score: float = 0.5
    awaiting_reply: bool = False

    @property
    def is_in_cooldown(self) -> bool:
        return time.time() < self.cooldown_until

    @property
    def cooldown_seconds_left(self) -> float:
        return max(0.0, self.cooldown_until - time.time())

    @property
    def can_initiate(self) -> bool:
        return (
            not self.is_in_cooldown
            and not self.awaiting_reply
            and self.engagement_score >= MIN_ENGAGEMENT_FOR_INITIATION
        )


class FriendRegistry:

    def __init__(self, db_path: str = DB_PATH):
        self._db = db_path
        self._sync_special_friends()

    # ── Special friend sync ───────────────────────────────────────

    def _sync_special_friends(self) -> None:
        """Load SPECIAL_FRIENDS config into DB on startup."""
        for sf in SPECIAL_FRIENDS:
            if sf["name"] == "REPLACE_NAME":
                continue  # skip placeholder
            fid = self._make_id(sf["name"], sf.get("phone",""), sf.get("instagram_id",""))
            self._upsert_friend(
                friend_id=fid,
                display_name=sf["name"],
                phone=sf.get("phone",""),
                instagram_id=sf.get("instagram_id",""),
                nickname=sf.get("nickname",""),
                platform=sf.get("platform","whatsapp"),
                special_mode=True,
            )
            self._upsert_vector(fid, sf["base_traits"], special_mode=True)

    # ── Friend CRUD ───────────────────────────────────────────────

    def get_or_create(self, identifier: str, platform: str = "whatsapp",
                      display_name: str = "") -> FriendProfile:
        """
        Look up friend by phone, instagram_id, or nickname.
        Creates a new normal-friend profile if not found.
        """
        friend = self._find_by_identifier(identifier)
        if friend:
            return friend

        # New friend — create normal profile
        fid = self._make_id(display_name or identifier, identifier, "")
        name = display_name or identifier
        self._upsert_friend(fid, name, phone=identifier if identifier.startswith("+") else "",
                             instagram_id=identifier if not identifier.startswith("+") else "",
                             platform=platform)
        self._upsert_vector(fid, DEFAULT_NORMAL_TRAITS, special_mode=False)
        return self.get_profile(fid)

    def get_profile(self, friend_id: str) -> Optional[FriendProfile]:
        con = connect(self._db)
        row = con.execute(
            "SELECT f.*, pv.humor,pv.caring,pv.formality,pv.emoji,pv.energy,"
            "pv.directness,pv.engagement_score,pv.cooldown_until,"
            "COALESCE(rq.awaiting_reply,0) as awaiting_reply "
            "FROM friends f "
            "LEFT JOIN personality_vectors pv ON pv.friend_id=f.friend_id "
            "LEFT JOIN reply_queue rq ON rq.friend_id=f.friend_id "
            "WHERE f.friend_id=?", (friend_id,)
        ).fetchone()
        con.close()
        if not row:
            return None
        return self._row_to_profile(row)

    def all_friends(self) -> list[FriendProfile]:
        con = connect(self._db)
        rows = con.execute(
            "SELECT f.*, pv.humor,pv.caring,pv.formality,pv.emoji,pv.energy,"
            "pv.directness,pv.engagement_score,pv.cooldown_until,"
            "COALESCE(rq.awaiting_reply,0) as awaiting_reply "
            "FROM friends f "
            "LEFT JOIN personality_vectors pv ON pv.friend_id=f.friend_id "
            "LEFT JOIN reply_queue rq ON rq.friend_id=f.friend_id"
        ).fetchall()
        con.close()
        return [self._row_to_profile(r) for r in rows]

    def set_special_mode(self, friend_id: str, special: bool) -> None:
        con = connect(self._db)
        con.execute("UPDATE friends SET special_mode=? WHERE friend_id=?",
                    (int(special), friend_id))
        con.execute("UPDATE personality_vectors SET special_mode=? WHERE friend_id=?",
                    (int(special), friend_id))
        con.commit()
        con.close()

    # ── Cooldown management ───────────────────────────────────────

    def set_cooldown(self, friend_id: str, special: bool = False) -> None:
        duration = SPECIAL_COOLDOWN_S if special else NORMAL_COOLDOWN_S
        until = time.time() + duration
        con = connect(self._db)
        con.execute("UPDATE personality_vectors SET cooldown_until=? WHERE friend_id=?",
                    (until, friend_id))
        con.commit()
        con.close()

    def clear_cooldown(self, friend_id: str) -> None:
        con = connect(self._db)
        con.execute("UPDATE personality_vectors SET cooldown_until=0 WHERE friend_id=?",
                    (friend_id,))
        con.commit()
        con.close()

    def is_in_cooldown(self, friend_id: str) -> bool:
        con = connect(self._db)
        row = con.execute("SELECT cooldown_until FROM personality_vectors WHERE friend_id=?",
                          (friend_id,)).fetchone()
        con.close()
        if not row:
            return False
        return time.time() < (row["cooldown_until"] or 0)

    # ── Awaiting reply ────────────────────────────────────────────

    def set_awaiting_reply(self, friend_id: str, awaiting: bool) -> None:
        con = connect(self._db)
        con.execute("""
            INSERT INTO reply_queue (friend_id, awaiting_reply, last_sent)
            VALUES (?, ?, ?)
            ON CONFLICT(friend_id) DO UPDATE SET
                awaiting_reply=excluded.awaiting_reply,
                last_sent=CASE WHEN excluded.awaiting_reply=1 THEN unixepoch() ELSE last_sent END
        """, (friend_id, int(awaiting), time.time()))
        con.commit()
        con.close()

    def mark_reply_received(self, friend_id: str) -> None:
        con = connect(self._db)
        con.execute("""
            INSERT INTO reply_queue (friend_id, awaiting_reply, last_received)
            VALUES (?, 0, ?)
            ON CONFLICT(friend_id) DO UPDATE SET
                awaiting_reply=0, last_received=excluded.last_received
        """, (friend_id, time.time()))
        con.commit()
        con.close()

    # ── Trait update ──────────────────────────────────────────────

    def update_trait(self, friend_id: str, trait: str, new_val: float) -> None:
        LOCKED_TRAITS = {"aggression","manipulation","dependency","jealousy","conflict_escalation"}
        if trait in LOCKED_TRAITS:
            raise ValueError(f"Trait '{trait}' is hard-locked at 0.0.")
        val = clamp(new_val)
        con = connect(self._db)
        con.execute(f"UPDATE personality_vectors SET {trait}=?, updated_at=? WHERE friend_id=?",
                    (val, time.time(), friend_id))
        con.commit()
        con.close()

    def update_engagement(self, friend_id: str, new_score: float) -> None:
        self.update_trait(friend_id, "engagement_score", new_score)

    def get_traits(self, friend_id: str) -> dict:
        con = connect(self._db)
        row = con.execute("SELECT * FROM personality_vectors WHERE friend_id=?",
                          (friend_id,)).fetchone()
        con.close()
        if not row:
            return {}
        return dict(row)

    # ── Matching ──────────────────────────────────────────────────

    def _find_by_identifier(self, identifier: str) -> Optional[FriendProfile]:
        con = connect(self._db)
        # Try exact phone match
        row = con.execute(
            "SELECT friend_id FROM friends WHERE phone=? OR instagram_id=?",
            (identifier, identifier)
        ).fetchone()
        if row:
            con.close()
            return self.get_profile(row["friend_id"])

        # Try nickname fuzzy match (similarity > 0.8)
        rows = con.execute("SELECT friend_id, nickname FROM friends WHERE nickname!=''").fetchall()
        con.close()
        best_score = 0.0
        best_id = None
        for r in rows:
            score = difflib.SequenceMatcher(None,
                        identifier.lower(), r["nickname"].lower()).ratio()
            if score > best_score and score >= 0.80:
                best_score = score
                best_id = r["friend_id"]
        if best_id:
            return self.get_profile(best_id)
        return None

    # ── DB helpers ────────────────────────────────────────────────

    def _upsert_friend(self, friend_id: str, display_name: str,
                        phone: str = "", instagram_id: str = "",
                        nickname: str = "", platform: str = "whatsapp",
                        special_mode: bool = False) -> None:
        con = connect(self._db)
        # Use NULL for empty unique fields to avoid UNIQUE constraint conflicts
        phone_val = phone if phone else None
        insta_val = instagram_id if instagram_id else None
        con.execute("""
            INSERT INTO friends (friend_id, display_name, phone, instagram_id,
                                  nickname, platform, special_mode)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(friend_id) DO UPDATE SET
                phone=COALESCE(excluded.phone, phone),
                instagram_id=COALESCE(excluded.instagram_id, instagram_id),
                nickname=COALESCE(NULLIF(excluded.nickname,''), nickname),
                special_mode=excluded.special_mode
        """, (friend_id, display_name, phone_val, insta_val, nickname,
              platform, int(special_mode)))
        con.commit()
        con.close()

    def _upsert_vector(self, friend_id: str, traits: dict,
                        special_mode: bool = False) -> None:
        t = {k: clamp(v) for k, v in traits.items()}
        con = connect(self._db)
        con.execute("""
            INSERT INTO personality_vectors
                (friend_id, humor, caring, formality, emoji, energy, directness,
                 engagement_score, special_mode)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(friend_id) DO UPDATE SET
                humor=excluded.humor, caring=excluded.caring,
                formality=excluded.formality, emoji=excluded.emoji,
                energy=excluded.energy, directness=excluded.directness,
                special_mode=excluded.special_mode,
                updated_at=unixepoch()
        """, (friend_id,
              t.get("humor",0.5), t.get("caring",0.5), t.get("formality",0.4),
              t.get("emoji",0.3), t.get("energy",0.5), t.get("directness",0.5),
              t.get("engagement_score",0.5), int(special_mode)))
        con.commit()
        con.close()

    def _row_to_profile(self, row) -> FriendProfile:
        d = dict(row)
        return FriendProfile(
            friend_id=d["friend_id"],
            display_name=d["display_name"],
            phone=d.get("phone",""),
            instagram_id=d.get("instagram_id",""),
            nickname=d.get("nickname",""),
            platform=d.get("platform","whatsapp"),
            special_mode=bool(d.get("special_mode",0)),
            traits={
                "humor":      d.get("humor",0.5),
                "caring":     d.get("caring",0.5),
                "formality":  d.get("formality",0.4),
                "emoji":      d.get("emoji",0.3),
                "energy":     d.get("energy",0.5),
                "directness": d.get("directness",0.5),
            },
            cooldown_until=d.get("cooldown_until",0.0) or 0.0,
            engagement_score=d.get("engagement_score",0.5) or 0.5,
            awaiting_reply=bool(d.get("awaiting_reply",0)),
        )

    @staticmethod
    def _make_id(name: str, phone: str, insta: str) -> str:
        base = phone or insta or name
        return base.strip().lower().replace(" ","_").replace("+","").replace("@","_at_")[:32]
