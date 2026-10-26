import re

import pytest

from eplan_connection import cs_escape


def test_none_returns_empty_string():
    assert cs_escape(None) == ""


@pytest.mark.parametrize("value, expected", [(42, "42"), (1.5, "1.5"), (True, "True")])
def test_non_strings_are_converted_with_str(value, expected):
    assert cs_escape(value) == expected


def test_plain_text_is_unchanged_and_not_quoted():
    assert cs_escape("Hello World äöü") == "Hello World äöü"


@pytest.mark.parametrize("raw, escaped", [
    ("\\", "\\\\"),
    ('"', '\\"'),
    ("\n", "\\n"),
    ("\r", "\\r"),
    ("\t", "\\t"),
    ('C:\\a "b"\r\n', 'C:\\\\a \\"b\\"\\r\\n'),
])
def test_named_escapes(raw, escaped):
    assert cs_escape(raw) == escaped


@pytest.mark.parametrize("raw, escaped", [
    ("\x00", "\\u0000"),
    ("\x1f", "\\u001f"),
    ("\x0b", "\\u000b"),
    ("\u0085", "\\u0085"),
    ("\u2028", "\\u2028"),
    ("\u2029", "\\u2029"),
])
def test_control_chars_and_line_terminators_are_unicode_escaped(raw, escaped):
    assert cs_escape(raw) == escaped


def test_space_and_del_are_not_escaped():
    # 0x20 is the first non-control character; 0x7f is not a C# line terminator
    assert cs_escape(" \x7f") == " \x7f"


def _terminates_cs_literal(escaped: str) -> bool:
    """True if `escaped` would end or break a C# regular string literal."""
    i = 0
    while i < len(escaped):
        ch = escaped[i]
        if ch == "\\":
            i += 2
            continue
        if ch == '"' or ch in "\r\n\u0085\u2028\u2029":
            return True
        i += 1
    return False


@pytest.mark.parametrize("payload", [
    '"); System.IO.File.Delete("x"); //',
    '\\"); evil(); //',
    '\\\\"; evil();',
    'a\nb"; evil(); "',
    'x\u2028"); evil(); //',
    '\\',
    'trailing backslash\\',
])
def test_escaped_value_cannot_terminate_literal(payload):
    escaped = cs_escape(payload)
    assert not _terminates_cs_literal(escaped)
    # a trailing lone backslash would swallow the closing quote
    assert not re.search(r"(?<!\\)(\\\\)*\\$", escaped)
