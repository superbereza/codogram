"""Magic names for thread naming."""
import random
import uuid

MAGIC_NAMES = [
    "arcane", "mystic", "ethereal", "celestial", "phantom",
    "cosmic", "astral", "enigmatic", "luminous", "spectral",
    "sublime", "radiant", "obscure", "cryptic", "eldritch",
    "prismatic", "nebulous", "transcendent", "immortal", "mythic",
    "ancient", "eternal", "infinite", "quantum", "stellar",
    "lunar", "solar", "void", "nexus", "apex",
]


def get_random_magic_name(excluded: set[str] | None = None) -> str:
    """Get a random magic name not in excluded set."""
    excluded = excluded or set()
    available = [n for n in MAGIC_NAMES if n not in excluded]
    if not available:
        return uuid.uuid4().hex[:8]
    return random.choice(available)
