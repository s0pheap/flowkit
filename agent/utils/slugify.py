"""Slugify utility for project output directory names."""
import hashlib
import re
import unicodedata


def slugify(text: str) -> str:
    """Convert text to a clean directory-safe slug.

    Strip diacritics, lowercase, replace non-alphanumeric with _, collapse multiples.

    A name with no ASCII letters or digits at all — Korean, Khmer, or pure
    punctuation — would otherwise fold to the empty string, which is not a
    directory name: ``OUTPUT_DIR / ""`` is ``OUTPUT_DIR`` itself, so the project
    would write into the output root and ``auth.require_output_path`` would
    accept *every* path under it. Such names fall back to a short digest of the
    name, which keeps distinct names in distinct directories.

    Examples:
        "Chiến dịch giải cứu F-15E" → "chien_dich_giai_cuu_f_15e"
        "A Day in My Life (Realistic)" → "a_day_in_my_life_realistic"
        "Pippip's Fish Market" → "pippips_fish_market"
        "한국어 프로젝트" → "p_d2504167"
    """
    # Vietnamese Đ/đ (D-stroke) doesn't decompose via NFKD — map manually
    original = text
    text = text.replace("Đ", "D").replace("đ", "d")
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        digest = hashlib.sha256(original.encode("utf-8")).hexdigest()[:8]
        return f"p_{digest}"
    return text
