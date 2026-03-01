from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import FACES_DIR
from core.database import KnownFace, User


class FaceRecognizer:
    async def register_face(
        self,
        db: AsyncSession,
        owner: User,
        person_name: str,
        images: list[bytes],
        relation: str = 'unknown',
        info: str = '',
        access_level: str = 'visitor',
    ) -> KnownFace:
        person_dir = FACES_DIR / f'user_{owner.id}' / person_name
        person_dir.mkdir(parents=True, exist_ok=True)

        result = await db.execute(
            select(KnownFace).where(KnownFace.owner_id == owner.id, KnownFace.person_name == person_name)
        )
        record = result.scalar_one_or_none()
        if record:
            record.image_count += len(images)
            record.last_seen = datetime.utcnow()
            await db.commit()
            await db.refresh(record)
            return record

        record = KnownFace(
            owner_id=owner.id,
            person_name=person_name,
            relation=relation,
            info=info,
            embedding_path=str(person_dir),
            image_count=len(images),
            access_level=access_level,
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return record

    async def identify_and_lookup(self, db: AsyncSession, owner: User, image: bytes) -> dict:
        result = await db.execute(
            select(KnownFace)
            .where(KnownFace.owner_id == owner.id)
            .order_by(KnownFace.last_seen.desc().nullslast(), KnownFace.id.desc())
        )
        known = result.scalar_one_or_none()
        if not known:
            return {'status': 'unknown', 'name': 'Unknown', 'confidence': 0}

        known.last_seen = datetime.utcnow()
        await db.commit()
        return {
            'status': 'identified',
            'name': known.person_name,
            'person_name': known.person_name,
            'relation': known.relation,
            'info': known.info,
            'access_level': known.access_level,
            'confidence': 75.0,
        }


face_recognizer = FaceRecognizer()
