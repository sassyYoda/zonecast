from pathlib import Path

from zonecast.text import spoken_text, spoken_word_count

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = REPO_ROOT / "examples" / "diffusion-overview-15min.md"


def test_strips_html_comments_including_multiline_state() -> None:
    md = "[HOST] Real prose.\n<!-- STATE after section 1:\n- words: 5 -->\nMore prose."
    out = spoken_text(md)
    assert "STATE" not in out
    assert "words" not in out
    assert "Real prose." in out
    assert "More prose." in out


def test_strips_headers() -> None:
    md = "# Title\n## Section 1: Foo [~600 words]\n[HOST] The prose."
    out = spoken_text(md)
    assert "Title" not in out
    assert "Section 1" not in out
    assert out == "The prose."


def test_strips_metadata_header_lines() -> None:
    md = "**Driving question:** How?\n**Format:** solo\n[HOST] Body."
    out = spoken_text(md)
    assert "Driving question" not in out
    assert "solo" not in out
    assert out == "Body."


def test_strips_speaker_tags() -> None:
    md = "[HOST] one two.\n[GUEST] three four."
    out = spoken_text(md)
    assert "[HOST]" not in out
    assert "[GUEST]" not in out
    assert out == "one two. three four."


def test_strips_pause_markers() -> None:
    md = "[HOST] before [PAUSE:short] middle [PAUSE:long] after."
    out = spoken_text(md)
    assert "PAUSE" not in out
    assert "[" not in out


def test_strips_italic_emphasis_markers() -> None:
    # Acceptance: no italic emphasis survives into spoken_text() (SKILL.md Pass 4).
    md = "[HOST] She recovers *a* painting, not *the* original."
    out = spoken_text(md)
    assert "*" not in out
    assert out == "She recovers a painting, not the original."


def test_collapses_whitespace() -> None:
    md = "[HOST] one\n\n\ntwo    three"
    assert spoken_text(md) == "one two three"


def test_empty_input() -> None:
    assert spoken_text("") == ""
    assert spoken_word_count("") == 0


def test_example_spoken_word_count_in_contract_band() -> None:
    raw = EXAMPLE.read_text()
    count = spoken_word_count(raw)
    # Raw is ~2,340; spoken ~2,268. Below ~2,200 means we stripped real prose;
    # near 2,340 means we did not strip enough (FR-5a correctness anchor).
    assert 2200 <= count <= 2320, f"spoken word count {count} outside 2200-2320"
