"""Magic names for thread naming."""
import random

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
        # Try with suffixes
        for suffix in range(2, 100):
            for base_name in MAGIC_NAMES:
                candidate = f"{base_name}-{suffix}"
                if candidate not in excluded:
                    return candidate
        raise ValueError("All magic names exhausted")
    return random.choice(available)
