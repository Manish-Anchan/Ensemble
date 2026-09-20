import pytest
import json
from ensemble.director.models import ScreenplayLine, Screenplay
from ensemble.director.director import SceneDirector
from ensemble.producer.models import CastSheet, CharacterProfile


def test_screenplay_models():
    """Verifies that ScreenplayLine and Screenplay serialize and deserialize properly."""
    line1 = ScreenplayLine(
        speaker="narrator",
        text="The sun set behind the hills.",
        emotion="wistful",
        speed=1.0,
        pause_after_ms=500
    )
    line2 = ScreenplayLine(
        speaker="char_tom",
        text="What are you looking at?",
        emotion="arrogant",
        speed=1.05,
        pause_after_ms=400
    )

    screenplay = Screenplay(
        chapter_index=1,
        scene_index=2,
        lines=[line1, line2]
    )

    assert screenplay.total_words == 11
    assert screenplay.speaker_counts == {"narrator": 1, "char_tom": 1}

    # Serialization
    data = screenplay.to_dict()
    assert data["chapter_index"] == 1
    assert len(data["lines"]) == 2

    # Deserialization
    loaded = Screenplay.from_dict(data)
    assert loaded.scene_index == 2
    assert loaded.lines[1].speaker == "char_tom"
    assert loaded.lines[1].emotion == "arrogant"


def test_scene_director_mock(monkeypatch):
    """Verifies that SceneDirector properly directs prose into Screenplay and performs JIT casting."""
    director = SceneDirector(api_key="mock-key")

    mock_llm_response = {
        "lines": [
            {
                "speaker": "narrator",
                "emotion": "measured",
                "text": "Nick looked across the dark water toward the green dock light.",
                "speed": 1.0,
                "pause_after_ms": 550
            },
            {
                "speaker": "char_tom",
                "emotion": "arrogant",
                "text": "Civilization is going to pieces.",
                "speed": 1.02,
                "pause_after_ms": 400
            },
            {
                "speaker": "char_catherine",
                "emotion": "lively",
                "text": "Do you live on Long Island too?",
                "speed": 1.0,
                "pause_after_ms": 400
            }
        ],
        "new_characters": [
            {
                "name": "Catherine",
                "gender": "female",
                "role": "supporting",
                "personality_traits": ["lively", "curious"]
            }
        ]
    }

    monkeypatch.setattr(
        director,
        "_call_with_retry",
        lambda messages: type(
            "MockResp",
            (),
            {
                "choices": [
                    type("Choice", (), {"message": type("Msg", (), {"content": json.dumps(mock_llm_response)})()})()
                ]
            },
        )(),
    )

    cast_sheet = CastSheet(
        book_title="The Great Gatsby",
        characters={
            "narrator": CharacterProfile(
                id="narrator",
                name="Nick Carraway",
                gender="male",
                age_group="adult",
                role="narrator",
                personality_traits=["observant"],
                aliases=["Nick"],
                voice_id="am_michael"
            ),
            "char_tom": CharacterProfile(
                id="char_tom",
                name="Tom Buchanan",
                gender="male",
                age_group="adult",
                role="antagonist",
                personality_traits=["arrogant"],
                aliases=["Tom"],
                voice_id="am_adam"
            ),
        }
    )

    screenplay, updated_cast = director.direct_scene(
        scene="Nick stood by the dock. Tom laughed loudly. Catherine asked a question.",
        cast_sheet=cast_sheet,
        chapter_index=1,
        scene_index=3,
    )

    assert len(screenplay.lines) == 3
    assert screenplay.lines[0].speaker == "narrator"
    assert screenplay.lines[1].speaker == "char_tom"
    assert screenplay.lines[2].speaker == "char_catherine"

    # Verify JIT dynamic character registration
    assert "char_catherine" in updated_cast.characters
    catherine = updated_cast.characters["char_catherine"]
    assert catherine.name == "Catherine"
    assert catherine.gender == "female"
    assert catherine.voice_id != "am_michael"  # Distinct from existing voices
    assert catherine.voice_id != "am_adam"
