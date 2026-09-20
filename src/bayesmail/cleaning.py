"""Corpus-specific repairs, normalization, and quality decisions."""

import base64
import re
import unicodedata

from .artifacts import sha256_bytes
from .email_parser import parse_email


RULE_VERSION = "clean-v1"
HTML_TAG = re.compile(
    r"</?(?:html|head|body|div|p|br|table|tr|td|script|style|font|a|span|img|li)\b[^>]*>",
    re.I,
)


def digest(raw):
    return sha256_bytes(raw)


def normalize(text):
    text = "".join(
        " "
        if char == "\ufffd" or unicodedata.category(char) in ("Cc", "Cf")
        else char
        for char in text
    )
    return " ".join(unicodedata.normalize("NFC", text).split())


def repair_raw(raw, identifier, overrides):
    edit = overrides.get(identifier)
    if not edit:
        return raw, None
    if digest(raw) != edit["raw_sha256"]:
        raise ValueError(f"{identifier}: reviewed override raw hash mismatch")
    action = edit["action"]
    if action == "truncate_body_tail":
        marker = bytes.fromhex(edit["marker_hex"])
        if not marker or raw.count(marker) != 1:
            raise ValueError(f"{identifier}: tail marker not unique")
        offset = raw.index(marker)
        separator = re.search(rb"\r?\n\r?\n", raw)
        if not separator or offset < separator.end():
            raise ValueError(f"{identifier}: tail marker is not in body")
        raw = raw[:offset]
    elif action == "repair_subject_fold":
        raw = repair_subject_fold(raw, required=True)
    elif action not in ("subject_charset", "quarantine", "force_html"):
        raise ValueError(f"Unknown reviewed action: {action}")
    return raw, edit


def repair_subject_fold(raw, required=False):
    separator = re.search(rb"\r?\n\r?\n", raw)
    header = raw[: separator.start()] if separator else raw
    pattern = (
        rb"(?im)^(Subject: =\?([^?\s]+)\?B\?)([A-Za-z0-9+/=]+)\r?\n"
        rb"([A-Za-z0-9+/=]+)\?=(?=\r?\n[A-Za-z][A-Za-z0-9-]*:)"
    )
    matches = list(re.finditer(pattern, header))
    if len(matches) != 1:
        if required:
            raise ValueError("Reviewed subject fold not found in header")
        return raw
    match = matches[0]
    try:
        base64.b64decode(match[3] + match[4], validate=True).decode(
            match[2].decode("ascii")
        )
    except (ValueError, UnicodeError, LookupError):
        if required:
            raise
        return raw
    return (
        raw[: match.start()]
        + match[1]
        + match[3]
        + match[4]
        + b"?="
        + raw[match.end() :]
    )


def clean_email(raw, identifier, label, overrides=None):
    if label not in ("ham", "spam"):
        raise ValueError("label must be ham or spam")
    original_hash = digest(raw)
    raw, edit = repair_raw(raw, identifier, overrides or {})
    actions, flags = [], []
    if edit:
        actions.append("reviewed_" + edit["action"])
    repaired = repair_subject_fold(raw)
    if repaired != raw:
        actions.append("strict_subject_fold_repair")
        raw = repaired
    parsed = parse_email(
        raw,
        identifier=identifier,
        subject_charset=(
            edit.get("charset")
            if edit and edit["action"] == "subject_charset"
            else None
        ),
        force_html=bool(edit and edit["action"] == "force_html"),
    )
    subject, body = parsed.subject, parsed.body
    actions.extend(parsed.actions)
    text = subject + body
    replacements = text.count("\ufffd")
    controls = sum(
        unicodedata.category(char) == "Cc" and char not in "\r\n\t" for char in text
    )
    if replacements:
        flags.append("replacement_character")
        actions.append("replacement_to_separator")
    if controls:
        flags.append("control_character")
        actions.append("control_to_separator")
    if any("\ue000" <= char <= "\uf8ff" for char in text):
        flags.append("private_use_character")
    status = "keep"
    if "\x00" in text or controls >= 8 or ("JFIF" in body and controls):
        flags.append("suspected_binary")
        status = "quarantine"
    if re.search(r"=\?[^?\s]+\?[bq]\?", subject, re.I):
        flags.append("unresolved_subject_encoding")
        status = "quarantine"
    if edit and edit["action"] == "quarantine":
        status = "quarantine"
        flags.append("review_pending")
    subject, body = normalize(subject), normalize(body)
    actions.append("nfc_whitespace_normalization")
    if not body:
        flags.append("empty_body")
        if subject:
            actions.append("subject_only")
    if not any(char.isalnum() for char in subject + body):
        flags.append("no_usable_text")
        status = "exclude"
    if HTML_TAG.search(body):
        flags.append("residual_html_heuristic")
    defects = list(parsed.mime_defects)
    if defects:
        flags.append("mime_defect")
    return dict(
        id=identifier,
        label=label,
        subject=subject,
        body=body,
        status=status,
        raw_sha256=original_hash,
        rules_version=RULE_VERSION,
        actions=sorted(set(actions)),
        quality_flags=sorted(set(flags)),
        replacements_before_normalization=replacements,
        controls_before_normalization=controls,
        parser_warnings=list(parsed.warnings),
        mime_defects=defects,
        review_reason=edit["reason"] if edit else None,
    )
