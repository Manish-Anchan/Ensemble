from dataclasses import dataclass
from typing import List, Dict, Optional


@dataclass(frozen=True)
class VoiceDescriptor:
    voice_id: str
    name: str
    gender: str          # "male" | "female"
    accent: str          # "american" | "british"
    age_group: str       # "young" | "adult" | "elderly"
    timbre: str          # "warm", "deep", "sharp", "gritty", "calm", "bright", "commanding"
    description: str


# Catalog of 28 core English voices available in Kokoro-82M
KOKORO_VOICE_CATALOG: Dict[str, VoiceDescriptor] = {
    # --- American Male ---
    "am_adam": VoiceDescriptor(
        voice_id="am_adam",
        name="Adam",
        gender="male",
        accent="american",
        age_group="adult",
        timbre="deep",
        description="Deep, authoritative, slightly gruff masculine voice. Great for rugged heroes, commanders, or weary detectives."
    ),
    "am_michael": VoiceDescriptor(
        voice_id="am_michael",
        name="Michael",
        gender="male",
        accent="american",
        age_group="adult",
        timbre="calm",
        description="Steady, warm, composed and articulate. Ideal for thoughtful protagonists, narrators, or professionals."
    ),
    "am_onyx": VoiceDescriptor(
        voice_id="am_onyx",
        name="Onyx",
        gender="male",
        accent="american",
        age_group="adult",
        timbre="commanding",
        description="Very deep baritone, commanding, imposing. Excellent for powerful antagonists, leaders, or judges."
    ),
    "am_fenrir": VoiceDescriptor(
        voice_id="am_fenrir",
        name="Fenrir",
        gender="male",
        accent="american",
        age_group="adult",
        timbre="gritty",
        description="Dark, gravelly, menacing and intense. Perfect for villains, rough rogues, or ruthless warriors."
    ),
    "am_liam": VoiceDescriptor(
        voice_id="am_liam",
        name="Liam",
        gender="male",
        accent="american",
        age_group="young",
        timbre="bright",
        description="Youthful, earnest, clear and dynamic. Great for young men, students, or hopeful adventurers."
    ),
    "am_puck": VoiceDescriptor(
        voice_id="am_puck",
        name="Puck",
        gender="male",
        accent="american",
        age_group="young",
        timbre="mischievous",
        description="Energetic, slightly raspy, playful. Fits tricksters, sidekicks, or humorous characters."
    ),
    "am_echo": VoiceDescriptor(
        voice_id="am_echo",
        name="Echo",
        gender="male",
        accent="american",
        age_group="adult",
        timbre="smooth",
        description="Smooth, cool, mid-tone masculine voice. Great for slick, enigmatic, or charming characters."
    ),
    "am_eric": VoiceDescriptor(
        voice_id="am_eric",
        name="Eric",
        gender="male",
        accent="american",
        age_group="adult",
        timbre="warm",
        description="Friendly, accessible, grounded everyday voice. Good for friends, shopkeepers, or relatable allies."
    ),
    "am_santa": VoiceDescriptor(
        voice_id="am_santa",
        name="Santa",
        gender="male",
        accent="american",
        age_group="elderly",
        timbre="booming",
        description="Warm, hearty, aged and resonant. Good for mentors, grandfathers, or jovial older figures."
    ),

    # --- American Female ---
    "af_bella": VoiceDescriptor(
        voice_id="af_bella",
        name="Bella",
        gender="female",
        accent="american",
        age_group="young",
        timbre="sharp",
        description="Sharp, lively, young, assertive and expressive. Perfect for quick-witted heroines, rogues, or modern young women."
    ),
    "af_sarah": VoiceDescriptor(
        voice_id="af_sarah",
        name="Sarah",
        gender="female",
        accent="american",
        age_group="adult",
        timbre="calm",
        description="Poised, intelligent, resolute and clear. Ideal for elegant protagonists, scientists, or sophisticated women."
    ),
    "af_nicole": VoiceDescriptor(
        voice_id="af_nicole",
        name="Nicole",
        gender="female",
        accent="american",
        age_group="adult",
        timbre="soft",
        description="Gentle, breathy, thoughtful, melancholic. Fits mysterious, romantic, or vulnerable characters."
    ),
    "af_sky": VoiceDescriptor(
        voice_id="af_sky",
        name="Sky",
        gender="female",
        accent="american",
        age_group="young",
        timbre="bright",
        description="Sunny, cheerful, sweet and animated. Fits optimistic daughters, young adventurers, or bright companions."
    ),
    "af_heart": VoiceDescriptor(
        voice_id="af_heart",
        name="Heart",
        gender="female",
        accent="american",
        age_group="adult",
        timbre="warm",
        description="Warm, empathetic, natural and inviting. Excellent for compassionate characters or female narrators."
    ),
    "af_alloy": VoiceDescriptor(
        voice_id="af_alloy",
        name="Alloy",
        gender="female",
        accent="american",
        age_group="adult",
        timbre="crisp",
        description="Crisp, efficient, direct and neutral. Fits officers, businesswomen, or no-nonsense specialists."
    ),
    "af_aoede": VoiceDescriptor(
        voice_id="af_aoede",
        name="Aoede",
        gender="female",
        accent="american",
        age_group="adult",
        timbre="melodic",
        description="Silky, melodic, alluring and graceful. Fits aristocrats, sirens, or charismatic figures."
    ),
    "af_kore": VoiceDescriptor(
        voice_id="af_kore",
        name="Kore",
        gender="female",
        accent="american",
        age_group="young",
        timbre="somber",
        description="Quiet, introspective, serious young woman. Fits troubled heroines or solemn scholars."
    ),
    "af_river": VoiceDescriptor(
        voice_id="af_river",
        name="River",
        gender="female",
        accent="american",
        age_group="adult",
        timbre="grounded",
        description="Mature, sensible, dependable female tone. Fits reliable allies, mothers, or steadfast companions."
    ),

    # --- British Male ---
    "bm_george": VoiceDescriptor(
        voice_id="bm_george",
        name="George",
        gender="male",
        accent="british",
        age_group="adult",
        timbre="warm",
        description="Classic British storyteller. Warm, scholarly, articulate, and distinguished. The definitive fiction narrator."
    ),
    "bm_daniel": VoiceDescriptor(
        voice_id="bm_daniel",
        name="Daniel",
        gender="male",
        accent="british",
        age_group="adult",
        timbre="crisp",
        description="Crisp, cultured, upper-class British gentleman. Great for nobility, aristocrats, or precise intellectuals."
    ),
    "bm_fable": VoiceDescriptor(
        voice_id="bm_fable",
        name="Fable",
        gender="male",
        accent="british",
        age_group="adult",
        timbre="theatrical",
        description="Rich, dramatic, expressive British tone. Perfect for theatrical characters, poets, or dramatic antagonists."
    ),
    "bm_lewis": VoiceDescriptor(
        voice_id="bm_lewis",
        name="Lewis",
        gender="male",
        accent="british",
        age_group="elderly",
        timbre="distinguished",
        description="Distinguished, measured, older British voice. Fits professors, seasoned judges, or veteran lords."
    ),

    # --- British Female ---
    "bf_emma": VoiceDescriptor(
        voice_id="bf_emma",
        name="Emma",
        gender="female",
        accent="british",
        age_group="adult",
        timbre="warm",
        description="Refined, warm, literate British voice. Beautiful for classic heroines, period drama narrators, or noblewomen."
    ),
    "bf_isabella": VoiceDescriptor(
        voice_id="bf_isabella",
        name="Isabella",
        gender="female",
        accent="british",
        age_group="young",
        timbre="aristocratic",
        description="Polished, haughty, high-society British female. Ideal for socialites, aristocrats, or proud heroines."
    ),
    "bf_alice": VoiceDescriptor(
        voice_id="bf_alice",
        name="Alice",
        gender="female",
        accent="british",
        age_group="young",
        timbre="clear",
        description="Clear, inquisitive, polite British young lady. Classic voice for young heroines or curious observers."
    ),
    "bf_lily": VoiceDescriptor(
        voice_id="bf_lily",
        name="Lily",
        gender="female",
        accent="british",
        age_group="young",
        timbre="gentle",
        description="Soft, gentle, delicate British female voice. Fits innocent, quiet, or ethereal characters."
    ),
}


def get_default_narrator_voice(preferred_accent: str = "british") -> str:
    """Returns the gold-standard default narrator voice."""
    return "bm_george" if preferred_accent == "british" else "am_michael"


def format_catalog_for_prompt() -> str:
    """Formats the voice catalog into a readable prompt block for the LLM."""
    lines = []
    for v in KOKORO_VOICE_CATALOG.values():
        lines.append(f"- `{v.voice_id}`: [{v.gender.upper()}, {v.accent.capitalize()}, {v.age_group}] {v.description}")
    return "\n".join(lines)
