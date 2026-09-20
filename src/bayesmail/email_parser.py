"""Policy-neutral MIME decoding shared by sampling and cleaning."""

import base64
import binascii
import re
import warnings
from dataclasses import dataclass
from email import policy
from email.header import decode_header
from email.parser import BytesParser
from html.parser import HTMLParser


BLOCK_TAGS = set(
    "p div br table tr td th li ul ol hr h1 h2 h3 h4 h5 h6 "
    "blockquote pre section article".split()
)
KNOWN_TAGS = BLOCK_TAGS | set(
    "html head title body script style a b i u em strong span font img meta "
    "link tbody thead tfoot center input form label option select o:p".split()
)
HIDDEN_TAGS = {"head", "title", "script", "style"}


@dataclass(frozen=True)
class ParsedEmail:
    subject: str
    body: str
    actions: tuple
    warnings: tuple
    mime_defects: tuple


def decode_bytes(raw, charset=None):
    for encoding in dict.fromkeys(filter(None, (charset, "utf-8", "gb18030"))):
        try:
            return raw.decode(encoding)
        except (UnicodeError, LookupError):
            pass
    warnings.warn(
        "无法完整解码邮件字段，已用替代字符标记；请检查原始邮件。",
        UnicodeWarning,
    )
    candidates = [raw.decode(enc, errors="replace") for enc in ("utf-8", "gb18030")]
    return min(candidates, key=lambda text: text.count("\ufffd"))


class _VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = []
        self.head_metadata = False

    def handle_starttag(self, tag, attrs):
        if tag == "body" and all(item in ("head", "title") for item in self.hidden):
            self.hidden = []
            self.head_metadata = False
        elif self.hidden == ["head"] and tag not in {
            "html", "head", "title", "script", "style", "meta", "link", "base",
            "noscript", "template",
        }:
            self.hidden = []
            self.head_metadata = False
        elif self.hidden == ["head"] and tag in {"meta", "link", "base"}:
            self.head_metadata = True
        if tag in HIDDEN_TAGS:
            self.hidden.append(tag)
        elif not self.hidden:
            if tag in BLOCK_TAGS:
                self.parts.append(" ")
            elif tag not in KNOWN_TAGS:
                self.parts.append(self.get_starttag_text())

    def handle_startendtag(self, tag, attrs):
        if tag not in HIDDEN_TAGS:
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in self.hidden:
            self.hidden = self.hidden[: self.hidden.index(tag)]
        elif not self.hidden:
            if tag in BLOCK_TAGS:
                self.parts.append(" ")
            elif tag not in KNOWN_TAGS:
                self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if self.hidden == ["head"] and data.strip() and not self.head_metadata:
            self.hidden = []
        if not self.hidden:
            self.parts.append(data)


def visible_html(text):
    parser = _VisibleHTML()
    parser.feed(text)
    parser.close()
    return "".join(parser.parts)


def decode_subject(message, override_charset=None):
    header = next(
        (value for key, value in message.raw_items() if key.lower() == "subject"),
        "",
    )
    chunks = []
    for value, charset in decode_header(header):
        if isinstance(value, bytes):
            chunks.append(
                value.decode(override_charset)
                if override_charset
                else decode_bytes(value, charset)
            )
        else:
            chunks.append(
                decode_bytes(value.encode("utf-8", errors="surrogateescape"))
            )
    return "".join(chunks)


def _decode_part(part, identifier, actions):
    payload = part.get_payload(decode=True) or b""
    if part.get("Content-Transfer-Encoding", "").strip().lower() == "base64":
        original = part._payload.encode("ascii", errors="surrogateescape")
        try:
            payload = base64.b64decode(b"".join(original.split()), validate=True)
        except (ValueError, binascii.Error):
            payload = original
            actions.append("invalid_base64_flat_fallback")
            warnings.warn(f"{identifier}: invalid base64 header; reading flat body")
    return decode_bytes(payload, part.get_content_charset())


def _looks_like_html(text):
    paired = (
        r"<(html|head|body|div|p|table|tr|td|script|style|font|a|span|li)"
        r"\b[^>]*>.*?</\1\s*>"
    )
    attributes = r"<(?:html|body|div|p|table|a|img|font|span)\s+[a-zA-Z][\w:-]*\s*="
    standalone = r"^\s*<(?:br|hr)\s*/?>\s*$"
    return bool(
        re.search(paired, text, re.I | re.S)
        or re.search(attributes, text, re.I)
        or re.search(standalone, text, re.I | re.M)
    )


def _prepare_body(text, declared_html, actions):
    if declared_html or _looks_like_html(text):
        start = re.search(r"<html\b", text, re.I)
        if start and start.start() > 0:
            prefix, suffix = text[: start.start()], text[start.start() :]
            if " ".join(prefix.split()) and " ".join(prefix.split()) == " ".join(
                visible_html(suffix).split()
            ):
                actions.append("identical_flat_alternative_removed")
                text = suffix
            else:
                actions.append("mixed_plain_html_preserved")
        actions.append("html_visible_text")
        text = visible_html(text)
    return text


def parse_email(raw, *, identifier, subject_charset=None, force_html=False):
    actions = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        message = BytesParser(policy=policy.default).parsebytes(raw)
        subject = decode_subject(message, subject_charset)
        part = message.get_body(preferencelist=("plain", "html"))
        if (
            part is None
            and not message.is_multipart()
            and message.get_content_maintype() == "multipart"
            and message.get_content_disposition() != "attachment"
        ):
            part = message
            actions.append("flat_multipart_fallback")
            warnings.warn(
                f"{identifier}: multipart header has no boundaries; reading flat body"
            )
        body = ""
        if part is not None and not part.get_filename():
            body = _decode_part(part, identifier, actions)
            body = _prepare_body(
                body,
                part.get_content_type() == "text/html" or force_html,
                actions,
            )
        if not " ".join(body.split()):
            alternative = message.get_body(preferencelist=("html",))
            if (
                alternative is not None
                and alternative is not part
                and not alternative.get_filename()
            ):
                body = _prepare_body(
                    _decode_part(alternative, identifier, actions), True, actions
                )
                actions.append("empty_plain_html_fallback")
        defects = sorted(
            {type(defect).__name__ for item in message.walk() for defect in item.defects}
        )
    return ParsedEmail(
        subject=subject,
        body=body,
        actions=tuple(actions),
        warnings=tuple(str(item.message) for item in caught),
        mime_defects=tuple(defects),
    )
