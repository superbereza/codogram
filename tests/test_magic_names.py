# tests/test_magic_names.py
def test_get_random_magic_name():
    from codogram.magic_names import get_random_magic_name
    name = get_random_magic_name()
    assert isinstance(name, str)
    assert len(name) > 0

def test_get_random_magic_name_excludes():
    from codogram.magic_names import get_random_magic_name, MAGIC_NAMES
    # Exclude all but one
    excluded = set(MAGIC_NAMES[:-1])
    name = get_random_magic_name(excluded)
    assert name == MAGIC_NAMES[-1]


def test_magic_names_suffix_fallback():
    from codogram.magic_names import get_random_magic_name, MAGIC_NAMES

    # All base names taken
    excluded = set(MAGIC_NAMES)
    name = get_random_magic_name(excluded)

    # Should return name with suffix
    assert "-" in name
    base, suffix = name.rsplit("-", 1)
    assert base in MAGIC_NAMES
    assert suffix.isdigit()
