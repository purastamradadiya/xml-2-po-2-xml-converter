#!/usr/bin/env python3
"""Convert RimWorld XML translation files to .po format for translation."""

import os
import re
import sys

LANGUAGES_DIR = "Languages/Russian"
PO_DIR = "po"


def _split_li_items(text):
    """Split text containing <li> elements into a list of inner contents."""
    return [m.group(1) for m in re.finditer(r"<li>(.*?)</li>", text, re.DOTALL)]


def escape_po(text):
    """Escape text for .po file msgid/msgstr value.

    XML stores line breaks as literal \\n (two chars).  We convert these
    to actual newlines first, then let the PO escaping turn them into
    the \\n PO newline escape.  This way PO editors display line breaks
    naturally to the translator.

    Escaping order (critical):
      1. literal \\n (two chars) -> actual newline
      2. remaining \\ -> \\\\        (standalone backslashes)
      3. \" -> \\"                   (quotes)
      4. actual newline -> \\n       (PO newline escape)
    """
    text = text.replace("\\n", "\n")
    text = text.replace("\\", "\\\\")
    text = text.replace('"', '\\"')
    text = text.replace("\n", "\\n")
    return text


def parse_xml_entries(filepath):
    """Parse XML translation file, extracting entries and comments.

    Uses re.DOTALL to handle multiline EN comments and XML values
    containing child elements (<li> items in rulesStrings, etc.).

    Returns (def_ref, entries) where:
      def_ref: str -- the Defs reference comment or empty string
      entries: list of (xml_key, english_text, russian_text)
    """
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    def_ref = ""
    entries = []

    # Def source reference comment
    m = re.search(r"<!--\s*(Defs\\.*?)-->", content)
    if m:
        def_ref = "<!-- " + m.group(1).strip() + " -->"

    # Strip LanguageData wrapper so DOTALL regex matches child elements, not the root
    inner_match = re.search(r"<LanguageData>(.*)</LanguageData>", content, re.DOTALL)
    inner = inner_match.group(1) if inner_match else content

    # Match paired EN comment + XML element (multiline with DOTALL).
    # The backreference (\2) ensures the closing tag matches the opening tag.
    pattern = re.compile(
        r"<!--\s*EN:\s*(.*?)\s*-->\s*"
        r"<([A-Za-z_][A-Za-z0-9_.]*)>(.*?)</\2>",
        re.DOTALL
    )

    for m in pattern.finditer(inner):
        en_text = m.group(1).strip()
        xml_key = m.group(2)
        xml_value = m.group(3).strip()
        if en_text:
            entries.append((xml_key, en_text, xml_value))

    return def_ref, entries


def convert_all():
    xml_dir = LANGUAGES_DIR
    po_base = PO_DIR

    count_total = 0
    count_files = 0

    for root, dirs, files in os.walk(xml_dir):
        for filename in sorted(files):
            if not filename.endswith(".xml"):
                continue

            xml_path = os.path.join(root, filename)
            rel_path = os.path.relpath(xml_path, xml_dir)
            po_path = os.path.join(po_base, rel_path).replace(".xml", ".po")

            os.makedirs(os.path.dirname(po_path), exist_ok=True)

            def_ref, entries = parse_xml_entries(xml_path)
            if not entries:
                continue

            with open(po_path, "w", encoding="utf-8") as po:
                po.write("# Rimhammer - The End Times - Skaven\n")
                po.write("# Russian translation\n")
                po.write(f"# Source: {rel_path}\n")
                po.write("#\n")
                if def_ref:
                    po.write(f"#. {def_ref}\n")
                po.write("#\n")
                po.write('msgid ""\n')
                po.write('msgstr ""\n')
                po.write('"Content-Type: text/plain; charset=UTF-8\\n"\n')
                po.write('"Content-Transfer-Encoding: 8bit\\n"\n')
                po.write("\n")

                for xml_key, en_text, ru_text in entries:
                    if not en_text:
                        continue

                    li_items = _split_li_items(ru_text)
                    if li_items:
                        en_items = _split_li_items(en_text)
                        for i, (ru_item, en_item) in enumerate(
                            zip(li_items, en_items), 1
                        ):
                            sub_key = f"{xml_key}.{i}"
                            po.write(f'msgctxt "{sub_key}"\n')
                            po.write(f'msgid "{escape_po(en_item)}"\n')
                            po.write(f'msgstr ""\n')
                            po.write("\n")
                            count_total += 1
                    else:
                        po.write(f'msgctxt "{xml_key}"\n')
                        po.write(f'msgid "{escape_po(en_text)}"\n')
                        po.write(f'msgstr ""\n')
                        po.write("\n")
                        count_total += 1

            count_files += 1
            print(f"  {rel_path} -> po/{rel_path.replace('.xml', '.po')}")

    print(f"\nDone! {count_files} files, {count_total} entries converted.")


if __name__ == "__main__":
    convert_all()
