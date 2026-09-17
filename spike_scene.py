import os
import json
import time
import io
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
import soundfile as sf
from pydub import AudioSegment
from kokoro_onnx import Kokoro

load_dotenv()



SAMPLE_PROSE = """
Rain battered the stained-glass windows of the cathedral as Thorne knelt beside the shattered altar.
Behind him, Silvia stepped out from the shadows, her trench coat dripping with water.
"You shouldn't have come alone, Thorne," Silvia said, raising her revolver with steady hands. "Some secrets were meant to stay buried."
Thorne stood up slowly, brushing plaster dust from his coat. "Is that what you told the Bishop before you threw him from the bell tower?"
Silvia's expression hardened. "The Bishop was a fanatic. He was going to burn the whole city down."
A sudden flash of lightning illuminated the nave, followed by a deafening crash of thunder that shook the stone floor.
"""


VOICE_MAP = {
    "narrator": "bm_george",   # Warm British male storyteller
    "thorne": "am_adam",       # Deep, gritty detective
    "silvia": "af_sarah",      # Resolute, cool-headed female
}

def direct_scene(prose: str) -> list[dict]:
    """
    Calls the LLM Scene Director to turn raw prose into a structured screenplay.
    """
    client = OpenAI(
        api_key=os.getenv("GROQ_API_KEY"),
        base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    )
    

    system_prompt = """You are an elite Audio Drama Scene Director.
Your job is to convert narrative fiction prose into a screenplay JSON for multiple voice actors.

RULES:
1. Identify each spoken line and narrative block.
2. Speakers must be: "narrator", or the character's lowercase name (e.g. character's first or last name).
3. IMPORTANT: Strip out author tags from dialogue lines!
   - BAD: "Put the weapon down," Marcus whispered.
   - GOOD: "Put the weapon down." (The narrator handles description, or emotion handles delivery).
4. Assign an acting emotion tag (e.g. "tense", "whisper", "sarcastic", "urgent", "ominous", "cold", "grim").
5. Return ONLY a valid JSON array of objects with keys: "speaker", "emotion", "text".

Example:
[
  {"speaker": "narrator", "emotion": "grim", "text": "The rain fell heavily against the shattered glass."},
  {"speaker": "marcus", "emotion": "whisper", "text": "Put the weapon down."},
  {"speaker": "narrator", "emotion": "tense", "text": "Lyra stepped into the light, smiling faintly."},
  {"speaker": "lyra", "emotion": "cold", "text": "Make me, old friend."}
]"""

    print("🎬 1. Calling Scene Director LLM (Groq / Qwen)...")
    t0 = time.time()
    response = client.chat.completions.create(
        model=os.getenv("DIRECTOR_MODEL", "qwen/qwen3.8-27b"),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Convert this scene into a screenplay JSON:\n\n{prose.strip()}"}
        ],
        temperature=0.2,
        response_format={"type": "json_object"}
    )
    print(f"   Director finished in {time.time() - t0:.2f}s")
    
    raw_content = response.choices[0].message.content or "{}"
    parsed = json.loads(raw_content)

    if isinstance(parsed, dict):
        for val in parsed.values():
            if isinstance(val, list):
                return val
        return []
    return parsed if isinstance(parsed, list) else []

def synthesize_screenplay(screenplay: list[dict], output_path: str = "demo_scene.mp3"):
    """
    Synthesizes each line with Kokoro-82M and stitches with natural dialogue pauses using pydub.
    """
    model_path = os.getenv("KOKORO_MODEL_PATH", "models/kokoro-v1.0.onnx")
    voices_path = os.getenv("KOKORO_VOICES_PATH", "models/voices-v1.0.bin")
    
    print(f"🎙️ 2. Loading Kokoro-82M from {model_path}...")
    kokoro = Kokoro(model_path, voices_path)
    
    combined_audio = AudioSegment.empty()
    dialogue_pause = AudioSegment.silent(duration=400)  # 400ms between speakers
    narrative_pause = AudioSegment.silent(duration=550) # 550ms after narrative descriptions
    
    print("\n🎭 3. Synthesizing Actors:")
    t_start = time.time()
    
    for i, line in enumerate(screenplay, 1):
        speaker = line.get("speaker", "narrator").lower()
        emotion = line.get("emotion", "neutral")
        text = line.get("text", "").strip()
        if not text:
            continue
            
        voice = VOICE_MAP.get(speaker)
        if not voice:
            for key, v in VOICE_MAP.items():
                if key in speaker or speaker in key:
                    voice = v
                    break
        if not voice:
            voice = VOICE_MAP["narrator"]
        
        # Subtle speed adjustment based on emotion
        speed = 1.0
        if emotion in ("urgent", "panic", "shout"):
            speed = 1.1
        elif emotion in ("whisper", "grim", "ominous"):
            speed = 0.95
            
        print(f"   [{i}/{len(screenplay)}] {speaker.upper()} ({voice} | {emotion}): \"{text}\"")
        
        samples, sr = kokoro.create(text, voice=voice, speed=speed, lang="en-us")
        
        # Convert numpy samples to wav bytes for pydub
        wav_io = io.BytesIO()
        sf.write(wav_io, samples, sr, format="WAV")
        wav_io.seek(0)
        
        segment = AudioSegment.from_file(wav_io, format="wav")
        
        # Append audio line + appropriate pause
        combined_audio += segment
        if speaker == "narrator":
            combined_audio += narrative_pause
        else:
            combined_audio += dialogue_pause

    total_time = time.time() - t_start
    audio_duration_sec = len(combined_audio) / 1000.0
    
    print(f"\n⚡ Total synthesis time: {total_time:.2f}s for {audio_duration_sec:.2f}s of multi-voice audio!")
    
    # Export final audio drama file
    combined_audio.export(output_path, format="mp3", bitrate="192k")
    print(f"✨ Master audio saved to: {Path(output_path).resolve()}")

def main():
    print("=" * 60)
    print("ENSEMBLE: Multi-Voice Fiction Audio Drama Spike")
    print("=" * 60)
    
    # Step 1: Director LLM converts prose to screenplay
    screenplay = direct_scene(SAMPLE_PROSE)
    print(f"\n📜 Screenplay generated ({len(screenplay)} lines):")
    print(json.dumps(screenplay, indent=2))
    
    # Step 2: Synthesize and stitch multi-voice audio
    synthesize_screenplay(screenplay, "demo_scene.mp3")

if __name__ == "__main__":
    main()
