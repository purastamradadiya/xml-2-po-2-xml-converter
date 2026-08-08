#!/usr/bin/env python3
"""Convert translated .po files back to RimWorld XML translation format."""

import os
import re

LANGUAGES_DIR = "Languages/Russian"
PO_DIR = "po"


def unescape_po(text):
    """Unescape a PO msgid/msgstr value back to raw text.

    PO escapes handled:
      \\\\  ->  \\    (literal backslash)
      \\"  ->  "     (literal quote)
      \\n  ->  \\n   (newline, will be converted to \\n for XML)
      \\r  ->  \\r
      \\t  ->  \\t
    """
    result = []
    i = 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            if nxt == "\\":
                result.append("\\")
                i += 2
            elif nxt == '"':
                result.append('"')
                i += 2
            elif nxt == "n":
                result.append("\n")
                i += 2
            elif nxt == "r":
                result.append("\r")
                i += 2
            elif nxt == "t":
                result.append("\t")
                i += 2
            else:
                result.append(text[i])
                i += 1
        else:
            result.append(text[i])
            i += 1
    return "".join(result)


def parse_po_file(filepath):
    """Parse a .po file, return dict of {xml_key: translated_text}."""
    translations = {}

    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    current_key = ""
    current_msgstr = ""
    in_msgctxt = False
    in_msgstr = False
    in_header = True

    for line in lines:
        stripped = line.strip()

        if in_header:
            if stripped == "" or stripped.startswith("#"):
                continue
            if stripped.startswith("msgid") or stripped.startswith("msgctxt"):
                in_header = False
            else:
                continue

        # Extract XML key from msgctxt
        m = re.match(r'msgctxt\s+"(.+)"', stripped)
        if m:
            if current_key and current_msgstr:
                translations[current_key] = current_msgstr
            current_key = m.group(1)
            current_msgstr = ""
            in_msgctxt = True
            in_msgstr = False
            continue

        # Skip comments
        if stripped.startswith("#"):
            continue

        # msgid — skip (source text, not needed)
        if stripped.startswith("msgid"):
            in_msgctxt = False
            in_msgstr = False
            continue

        # msgstr — translated text
        m = re.match(r'msgstr\s+"(.*)"$', stripped)
        if m:
            current_msgstr = unescape_po(m.group(1))
            in_msgctxt = False
            in_msgstr = True
            continue

        # Continuation line
        if in_msgstr and stripped.startswith('"') and stripped.endswith('"'):
            current_msgstr += unescape_po(stripped[1:-1])
            continue

        # Empty line = end of entry
        if stripped == "" and current_key:
            if current_key and current_msgstr:
                translations[current_key] = current_msgstr
            current_key = ""
            current_msgstr = ""
            in_msgctxt = False
            in_msgstr = False

    # Last entry
    if current_key and current_msgstr:
        translations[current_key] = current_msgstr

    return translations


def _value_contains_xml_tags(value):
    """Check if a value contains XML child elements (e.g. <li>...</li>)."""
    return bool(re.search(r"<\w+[^>]*>", value))


def _xml_escape(text):
    """Minimal XML escaping: only & and < need escaping in text content."""
    return text.replace("&", "&amp;").replace("<", "&lt;")


def _prepare_text_value(value):
    """Convert a PO value back to XML text: newlines -> \\n, XML-escape."""
    return _xml_escape(value.replace("\n", "\\n"))


def _rebuild_li_value(translations, key):
    """Collect key.1, key.2, … from translations and assemble <li> structure.

    Returns None if no numbered keys are found.
    """
    items = []
    i = 1
    while True:
        sub_key = f"{key}.{i}"
        val = translations.get(sub_key)
        if val is None:
            break
        items.append(_prepare_text_value(val))
        i += 1
    if not items:
        return None
    return "\n\t\t".join(f"<li>{item}</li>" for item in items)


def update_xml_file(xml_path, translations):
    """Update XML file with translated values.  Preserves all comments.

    Handles both single-line values and multiline elements with child elements.
    Strips the LanguageData wrapper, processes child elements only, then puts
    the wrapper back so DOTALL does not consume the entire document in one match.
    """
    with open(xml_path, "r", encoding="utf-8") as f:
        content = f.read()

    updated_count = 0

    # Pattern for child elements inside LanguageData
    # Group 1: opening tag incl. <>,  Group 2: key name,  Group 3: inner content,
    # Group 4: closing tag incl. </>
    pattern = re.compile(
        r"(<([A-Za-z_][A-Za-z0-9_.]*)>)(.*?)(</\2>)",
        re.DOTALL
    )

    def replace_func(m):
        nonlocal updated_count
        key = m.group(2)
        old_value = m.group(3)
        old_stripped = old_value.strip()

        # Complex element (contains <li> children) → try split keys
        if _value_contains_xml_tags(old_value):
            new_value = _rebuild_li_value(translations, key)
            if new_value is not None and new_value != old_stripped:
                updated_count += 1
                return m.group(1) + new_value + m.group(4)
            return m.group(0)

        # Simple element → regular key lookup
        if key not in translations:
            return m.group(0)
        new_value = _prepare_text_value(translations[key])
        if new_value != old_stripped:
            updated_count += 1
            return m.group(1) + new_value + m.group(4)
        return m.group(0)

    # Strip LanguageData wrapper, process child elements, then rewrap
    wrapper_match = re.match(
        r"(.*?<LanguageData>)(.*)(</LanguageData>.*)", content, re.DOTALL
    )
    if wrapper_match:
        prefix = wrapper_match.group(1)
        inner = wrapper_match.group(2)
        suffix = wrapper_match.group(3)
        new_inner = pattern.sub(replace_func, inner)
        new_content = prefix + new_inner + suffix
    else:
        new_content = pattern.sub(replace_func, content)

    if updated_count > 0:
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(new_content)

    return updated_count


def convert_all():
    po_base = PO_DIR
    xml_dir = LANGUAGES_DIR

    total_updated = 0
    total_files = 0

    for root, dirs, files in os.walk(po_base):
        for filename in sorted(files):
            if not filename.endswith(".po"):
                continue

            po_path = os.path.join(root, filename)
            rel_path = os.path.relpath(po_path, po_base)
            xml_path = os.path.join(xml_dir, rel_path).replace(".po", ".xml")

            if not os.path.exists(xml_path):
                print(f"  WARNING: no matching XML for {po_path}")
                continue

            print(f"  {rel_path.replace('.po', '.xml')}")

            translations = parse_po_file(po_path)
            if not translations:
                print(f"    (no translated entries)")
                continue

            count = update_xml_file(xml_path, translations)
            total_updated += count
            total_files += 1
            print(f"    {count} entries updated")

    print(f"\nDone! {total_files} files, {total_updated} entries updated.")


if __name__ == "__main__":
    convert_all()
