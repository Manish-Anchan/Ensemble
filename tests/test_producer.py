import pytest
from pathlib import Path
from ensemble.producer.catalog import KOKORO_VOICE_CATALOG, get_default_narrator_voice
from ensemble.producer.models import CharacterProfile, CastSheet


def test_voice_catalog_integrity():
    """Verifies that all voices have valid metadata."""
    assert len(KOKORO_VOICE_CATALOG) >= 20
    assert "bm_george" in KOKORO_VOICE_CATALOG
    assert "am_adam" in KOKORO_VOICE_CATALOG
    assert "af_bella" in KOKORO_VOICE_CATALOG

    for vid, v in KOKORO_VOICE_CATALOG.items():
        assert v.gender in ("male", "female")
        assert v.accent in ("american", "british")
        assert v.age_group in ("young", "adult", "elderly")
        assert len(v.description) > 10


def test_cast_sheet_alias_resolution():
    """Verifies that CastSheet accurately maps character names and aliases to voice IDs."""
    characters = {
        "narrator": CharacterProfile(
            id="narrator",
            name="Story Narrator",
            gender="male",
            age_group="adult",
            role="narrator",
            personality_traits=["observant"],
            aliases=["narrator"],
            voice_id="bm_george",
        ),
        "char_gatsby": CharacterProfile(
            id="char_gatsby",
            name="Jay Gatsby",
            gender="male",
            age_group="adult",
            role="protagonist",
            personality_traits=["mysterious", "wealthy"],
            aliases=["Gatsby", "Mr. Gatsby", "Jay"],
            voice_id="am_michael",
        ),
        "char_daisy": CharacterProfile(
            id="char_daisy",
            name="Daisy Buchanan",
            gender="female",
            age_group="young",
            role="supporting",
            personality_traits=["charming", "careless"],
            aliases=["Daisy", "Mrs. Buchanan"],
            voice_id="af_bella",
        ),
        "char_tom": CharacterProfile(
            id="char_tom",
            name="Tom Buchanan",
            gender="male",
            age_group="adult",
            role="antagonist",
            personality_traits=["arrogant", "hulking"],
            aliases=["Tom", "Buchanan"],
            voice_id="am_adam",
        ),
    }

    sheet = CastSheet(book_title="The Great Gatsby", characters=characters)

    # Primary name
    assert sheet.get_voice_for_speaker("Jay Gatsby") == "am_michael"
    assert sheet.get_voice_for_speaker("Daisy Buchanan") == "af_bella"

    # Exact aliases
    assert sheet.get_voice_for_speaker("Mr. Gatsby") == "am_michael"
    assert sheet.get_voice_for_speaker("Gatsby") == "am_michael"
    assert sheet.get_voice_for_speaker("gatsby") == "am_michael"
    assert sheet.get_voice_for_speaker("Tom") == "am_adam"
    assert sheet.get_voice_for_speaker("Daisy") == "af_bella"

    # Narrator
    assert sheet.get_voice_for_speaker("narrator") == "bm_george"

    # Unknown character fallback
    assert sheet.get_voice_for_speaker("Random Butler") == "bm_george"


def test_cast_sheet_json_roundtrip(tmp_path: Path):
    """Verifies that CastSheet can serialize to and deserialize from JSON."""
    characters = {
        "narrator": CharacterProfile(
            id="narrator",
            name="Narrator",
            gender="male",
            age_group="adult",
            role="narrator",
            personality_traits=["calm"],
            aliases=["narrator"],
            voice_id="bm_george",
        ),
        "char_arthur": CharacterProfile(
            id="char_arthur",
            name="Arthur Pendelton",
            gender="male",
            age_group="adult",
            role="protagonist",
            personality_traits=["weary", "brave"],
            aliases=["Arthur", "Mr. Pendelton"],
            voice_id="am_adam",
        ),
    }

    sheet = CastSheet(book_title="The Lost Kingdom", characters=characters)
    json_path = tmp_path / "cast.json"
    sheet.save_json(json_path)

    loaded = CastSheet.load_json(json_path)
    assert loaded.book_title == "The Lost Kingdom"
    assert len(loaded.characters) == 2
    assert loaded.get_voice_for_speaker("Mr. Pendelton") == "am_adam"


def test_pick_unused_voice_avoids_collisions():
    """Verifies that _pick_unused_voice selects an unused voice and preserves the narrator."""
    from ensemble.producer.casting import CastingProducer

    producer = CastingProducer(api_key="mock-key")
    used = {"am_adam", "am_michael", "am_onyx"}
    voice = producer._pick_unused_voice("male", used)
    assert voice not in used
    assert voice != "bm_george"  # Narrator voice preserved

    female_used = {"af_bella", "af_sarah"}
    female_voice = producer._pick_unused_voice("female", female_used)
    assert female_voice not in female_used
    assert female_voice.startswith("af_") or female_voice.startswith("bf_")


def test_cast_scene_streaming(monkeypatch):
    """Verifies that cast_scene identifies newly discovered characters in a scene."""
    import json
    from ensemble.producer.casting import CastingProducer

    producer = CastingProducer(api_key="mock-key")

    mock_json = {
        "characters": [
            {
                "id": "char_jordan",
                "name": "Jordan Baker",
                "gender": "female",
                "role": "supporting",
                "personality_traits": ["aloof"],
                "aliases": ["Jordan", "Miss Baker"],
                "voice_id": "bf_isabella",
            }
        ]
    }

    monkeypatch.setattr(
        producer,
        "_call_with_retry",
        lambda messages: type(
            "MockResp",
            (),
            {
                "choices": [
                    type("Choice", (), {"message": type("Msg", (), {"content": json.dumps(mock_json)})()})()
                ]
            },
        )(),
    )

    existing_sheet = CastSheet(
        book_title="Gatsby",
        characters={
            "narrator": CharacterProfile(
                id="narrator",
                name="Narrator",
                gender="male",
                age_group="adult",
                role="narrator",
                personality_traits=[],
                aliases=[],
                voice_id="bm_george",
            )
        },
    )

    updated_sheet, new_chars = producer.cast_scene(
        book_title="Gatsby",
        scene_text="Jordan Baker stood up from the sofa.",
        existing_cast_sheet=existing_sheet,
    )

    assert len(new_chars) == 1
    assert new_chars[0].name == "Jordan Baker"
    assert new_chars[0].voice_id == "bf_isabella"
    assert "char_jordan" in updated_sheet.characters

