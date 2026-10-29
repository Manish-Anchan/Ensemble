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


def test_defensive_autocast_safeguard(monkeypatch):
    """Verifies that unregistered speakers in lines are auto-cast even if LLM omits new_characters."""
    director = SceneDirector(api_key="mock-key")

    # LLM outputs speaker "char_miss_jordan", but FORGETS new_characters list!
    mock_llm_response = {
        "lines": [
            {
                "speaker": "narrator",
                "emotion": "measured",
                "text": "Nick looked over.",
                "speed": 1.0,
                "pause_after_ms": 500,
            },
            {
                "speaker": "char_jordan",
                "emotion": "abrupt",
                "text": "Absolutely!",
                "speed": 1.0,
                "pause_after_ms": 400,
            },
        ],
        "new_characters": []  # Empty!
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
        book_title="Test Book",
        characters={
            "narrator": CharacterProfile(
                id="narrator", name="Narrator", gender="male", age_group="adult",
                role="narrator", personality_traits=[], aliases=[], voice_id="am_michael"
            )
        }
    )

    screenplay, updated_cast = director.direct_scene(
        scene="Miss Jordan said Absolutely with suddenness.",
        cast_sheet=cast_sheet,
        chapter_index=1,
        scene_index=1,
    )

    assert "char_jordan" in updated_cast.characters
    jordan = updated_cast.characters["char_jordan"]
    assert jordan.gender == "female"
    assert jordan.voice_id.startswith("af_")  # Assigned a female voice
    assert jordan.voice_id != "am_michael"     # Did not fall back to male narrator!


def test_director_empty_lines_narrator_fallback(monkeypatch):
    """Verifies that if the director LLM returns empty or malformed output, it falls back to a narrator line."""
    director = SceneDirector(api_key="mock-key")

    monkeypatch.setattr(
        director,
        "_call_with_retry",
        lambda messages: type(
            "MockResp",
            (),
            {
                "choices": [
                    type("Choice", (), {"message": type("Msg", (), {"content": "```json\n{\"lines\": []}\n```"})()})()
                ]
            },
        )(),
    )

    screenplay, _ = director.direct_scene(
        scene="It was a bright cold day in April, and the clocks were striking thirteen.",
        chapter_index=1,
        scene_index=1,
    )

    assert len(screenplay.lines) == 1
    assert screenplay.lines[0].speaker == "narrator"
    assert "striking thirteen" in screenplay.lines[0].text


def test_first_person_narrator_shared_voice(monkeypatch):
    """Verifies that when a character is the first-person narrator, dialogue lines resolve to narrator with the same voice."""
    director = SceneDirector(api_key="mock-key")

    mock_resp = {
        "lines": [
            {"speaker": "narrator", "text": "I looked across the bay.", "emotion": "reflective"},
            {"speaker": "char_nick", "text": "Is she from New York?", "emotion": "curious"},
        ],
        "new_characters": [
            {"name": "Nick Carraway", "gender": "male"}
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
                    type("Choice", (), {"message": type("Msg", (), {"content": json.dumps(mock_resp)})()})()
                ]
            },
        )(),
    )

    cast_sheet = CastSheet(
        book_title="The Great Gatsby",
        characters={
            "narrator": CharacterProfile(
                id="narrator", name="Nick Carraway", gender="male", age_group="adult",
                role="narrator", personality_traits=[], aliases=["Nick", "Carraway", "char_nick"],
                voice_id="am_michael"
            )
        }
    )

    screenplay, updated_cast = director.direct_scene(
        scene="I looked across the bay. 'Is she from New York?' I asked.",
        cast_sheet=cast_sheet,
        chapter_index=1,
        scene_index=1,
    )

    # Both lines should be unified under narrator with the same voice
    assert screenplay.lines[0].speaker == "narrator"
    assert screenplay.lines[1].speaker == "narrator"
    # No duplicate char_nick character profile created
    assert updated_cast.get_voice_for_speaker("narrator") == "am_michael"
    assert updated_cast.get_voice_for_speaker("char_nick") == "am_michael"


def test_previous_scene_context_and_presence(monkeypatch):
    """Verifies that previous_scene_context is incorporated into prompt and scene_characters_present is captured."""
    director = SceneDirector(api_key="mock-key")
    captured_messages = []

    mock_resp = {
        "scene_characters_present": ["narrator", "char_gatz"],
        "lines": [
            {"speaker": "narrator", "text": "I didn't know how to reach you.", "emotion": "concerned"},
            {"speaker": "char_gatz", "text": "It was a mad man.", "emotion": "frantic"},
        ],
        "new_characters": [
            {"name": "Henry C. Gatz", "gender": "male", "personality_traits": ["aged"]}
        ]
    }

    def mock_call(messages):
        captured_messages.extend(messages)
        return type(
            "MockResp",
            (),
            {
                "choices": [
                    type("Choice", (), {"message": type("Msg", (), {"content": json.dumps(mock_resp)})()})()
                ]
            },
        )()

    monkeypatch.setattr(director, "_call_with_retry", mock_call)

    prev_context = "Characters active in previous scene: Henry C. Gatz\nEnding of previous scene: 'I saw it in the Chicago newspaper,' he said."

    screenplay, updated_cast = director.direct_scene(
        scene="'I didn't know how to reach you.' 'It was a mad man,' he said.",
        previous_scene_context=prev_context,
        chapter_index=9,
        scene_index=3,
    )

    # Verify context was in the user message
    user_msg = next(m["content"] for m in captured_messages if m["role"] == "user")
    assert "[PREVIOUS SCENE CONTEXT" in user_msg
    assert "Henry C. Gatz" in user_msg
    assert "'I saw it in the Chicago newspaper,' he said." in user_msg

    # Verify scene_characters_present was preserved on Screenplay
    assert screenplay.scene_characters_present == ["narrator", "char_gatz"]
    assert len(screenplay.lines) == 2
    assert screenplay.lines[0].speaker == "narrator"
    assert screenplay.lines[1].speaker == "char_gatz"


def test_dynamic_scene_split_on_length(monkeypatch):
    """Verifies that an overflowing scene with finish_reason='length' dynamically splits into 2 parts and combines cleanly."""
    director = SceneDirector(api_key="mock-key")

    para1 = "The afternoon was dark and cloudy. " * 30
    para2 = "Tom stood by the mantelpiece looking sullen. " * 30
    full_prose = f"{para1}\n\n{para2}"

    call_count = 0
    captured_calls = []

    def mock_call(messages):
        nonlocal call_count
        call_count += 1
        captured_calls.append(messages)

        if call_count == 1:
            # First full call runs out of tokens
            return type(
                "MockResp",
                (),
                {
                    "choices": [
                        type(
                            "Choice",
                            (),
                            {
                                "finish_reason": "length",
                                "message": type("Msg", (), {"content": json.dumps({"lines": [{"speaker": "narrator", "text": "Part 1 truncated"}]})})()
                            }
                        )()
                    ]
                },
            )()
        elif call_count == 2:
            # Sub-call for Part 1
            return type(
                "MockResp",
                (),
                {
                    "choices": [
                        type(
                            "Choice",
                            (),
                            {
                                "finish_reason": "stop",
                                "message": type("Msg", (), {"content": json.dumps({
                                    "scene_characters_present": ["narrator"],
                                    "lines": [
                                        {"speaker": "narrator", "text": "The afternoon was dark."},
                                        {"speaker": "narrator", "text": "The clouds gathered."}
                                    ]
                                })})()
                            }
                        )()
                    ]
                },
            )()
        else:
            # Sub-call for Part 2 (includes context from Part 1)
            return type(
                "MockResp",
                (),
                {
                    "choices": [
                        type(
                            "Choice",
                            (),
                            {
                                "finish_reason": "stop",
                                "message": type("Msg", (), {"content": json.dumps({
                                    "scene_characters_present": ["char_tom"],
                                    "lines": [
                                        {"speaker": "char_tom", "text": "What do you want?"}
                                    ]
                                })})()
                            }
                        )()
                    ]
                },
            )()

    monkeypatch.setattr(director, "_call_with_retry", mock_call)

    screenplay, _ = director.direct_scene(
        scene=full_prose,
        chapter_index=1,
        scene_index=5,
    )

    assert call_count == 3  # 1 initial + 2 sub-part calls
    assert len(screenplay.lines) == 3
    assert screenplay.lines[0].text == "The afternoon was dark."
    assert screenplay.lines[1].text == "The clouds gathered."
    assert screenplay.lines[2].speaker == "char_tom"
    assert screenplay.lines[2].text == "What do you want?"
    assert screenplay.scene_characters_present == ["narrator", "char_tom"]


def test_scene_director_new_characters_as_strings(monkeypatch):
    """Verifies that SceneDirector handles new_characters as plain strings or char_ slugs without crashing."""
    director = SceneDirector(api_key="mock-key")

    mock_llm_response = {
        "scene_characters_present": ["narrator", "char_waiter"],
        "lines": [
            {
                "speaker": "narrator",
                "text": "The waiter stepped forward.",
                "emotion": "measured",
            },
            {
                "speaker": "char_waiter",
                "text": "Can I take your order, sir?",
                "emotion": "polite",
            }
        ],
        "new_characters": [
            "char_waiter",
            "Mrs. Wilson"
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
            )
        }
    )

    screenplay, updated_cast = director.direct_scene(
        scene="The waiter stepped forward. Can I take your order, sir?",
        cast_sheet=cast_sheet,
        chapter_index=1,
        scene_index=1,
    )

    assert len(screenplay.lines) == 2
    assert "char_waiter" in updated_cast.characters
    assert updated_cast.characters["char_waiter"].name == "Waiter"
    assert "char_mrs._wilson" in updated_cast.characters or "char_mrs_wilson" in updated_cast.characters
    assert screenplay.lines[1].speaker == "char_waiter"
