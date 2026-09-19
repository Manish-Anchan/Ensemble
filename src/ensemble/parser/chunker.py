import re
from typing import List
from ensemble.parser.models import SceneChunk


# Common scene break markers in fiction books
SCENE_BREAK_PATTERN = re.compile(
    r"^\s*(?:\*\s*\*\s*\*|\*\*\*|#\s*#\s*#|###|—\s*—\s*—|--+|~\s*~\s*~)\s*$",
    re.MULTILINE
)


def split_into_scenes(
    chapter_text: str,
    chapter_index: int,
    target_words: int = 600,
    min_words: int = 350,
    max_words: int = 900
) -> List[SceneChunk]:
    """
    Slices clean chapter prose into cohesive scene chunks (~400-800 words).
    Respects explicit scene break markers (* * *) and paragraph boundaries.
    Never splits across a dialogue or sentence mid-stream.
    """
    if not chapter_text.strip():
        return []

    # First, identify any explicit scene break dividers (like * * *)
    raw_sections = SCENE_BREAK_PATTERN.split(chapter_text)

    scenes: List[SceneChunk] = []
    global_para_idx = 0

    for section in raw_sections:
        section = section.strip()
        if not section:
            continue

        # Split section into paragraphs
        paragraphs = [p.strip() for p in section.split("\n\n") if p.strip()]
        if not paragraphs:
            continue

        current_paras: List[str] = []
        current_word_count = 0
        start_para = global_para_idx

        for p_idx, para in enumerate(paragraphs):
            p_words = len(para.split())

            # If adding this paragraph exceeds max_words and we already have enough words,
            # seal current scene and start a new one
            if current_word_count >= min_words and (current_word_count + p_words > max_words):
                scene_text = "\n\n".join(current_paras)
                scenes.append(
                    SceneChunk(
                        chapter_index=chapter_index,
                        scene_index=len(scenes) + 1,
                        text=scene_text,
                        word_count=current_word_count,
                        start_paragraph=start_para,
                        end_paragraph=global_para_idx - 1
                    )
                )
                current_paras = []
                current_word_count = 0
                start_para = global_para_idx

            current_paras.append(para)
            current_word_count += p_words
            global_para_idx += 1

            # If we reached our sweet spot target words, finish the scene
            if current_word_count >= target_words:
                scene_text = "\n\n".join(current_paras)
                scenes.append(
                    SceneChunk(
                        chapter_index=chapter_index,
                        scene_index=len(scenes) + 1,
                        text=scene_text,
                        word_count=current_word_count,
                        start_paragraph=start_para,
                        end_paragraph=global_para_idx - 1
                    )
                )
                current_paras = []
                current_word_count = 0
                start_para = global_para_idx

        # Flush any trailing paragraphs in this section
        if current_paras:
            # Only merge into previous scene if this was NOT an explicit scene break (* * *)
            # and the remaining snippet is extremely small
            is_explicit_scene_break = len(raw_sections) > 1
            if not is_explicit_scene_break and scenes and current_word_count < (min_words // 2):
                prev_scene = scenes[-1]
                prev_scene.text += "\n\n" + "\n\n".join(current_paras)
                prev_scene.word_count += current_word_count
                prev_scene.end_paragraph = global_para_idx - 1
            else:
                scene_text = "\n\n".join(current_paras)
                scenes.append(
                    SceneChunk(
                        chapter_index=chapter_index,
                        scene_index=len(scenes) + 1,
                        text=scene_text,
                        word_count=current_word_count,
                        start_paragraph=start_para,
                        end_paragraph=global_para_idx - 1
                    )
                )

    return scenes
