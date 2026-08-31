#!/usr/bin/env python3
"""Reject credentials and private AI translation endpoints before distribution."""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit
import zipfile


MAX_TEXT_SIZE = 8 * 1024 * 1024
ZERO_OID = "0" * 40
PLACEHOLDER_HOSTS = {"example.com", "api.example.com", "example.invalid"}
AI_SERVICE_HOST_PARTS = (
    "openai",
    "anthropic",
    "deepseek",
    "openrouter",
    "siliconflow",
    "dashscope",
    "moonshot",
    "bigmodel",
    "volcengine",
    "generativelanguage.googleapis",
)
PRIVATE_URL_CONTEXT = re.compile(
    r"(?i)(?:morph_ai_api_url|ai_translation_url|translation_api_url|"
    r"openai_base_url|ai_endpoint|translation_endpoint)"
)
URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
LITERAL_CREDENTIAL = re.compile(
    r"(?ix)\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|secret[_-]?key|"
    r"client[_-]?secret|password)\b\s*[:=]\s*[rubf]*([\"'])([^\r\n\"']{8,})\1"
)
PLACEHOLDER_VALUE = re.compile(
    r"(?i)^(?:your[_ -]|replace[_ -]|example|dummy|test|none|null|changeme|"
    r"\$\{|%[A-Z_]+%|os\.|env\.|getenv|self\.|preferences\.)"
)
HIGH_CONFIDENCE_PATTERNS = (
    (
        "private-key",
        re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    ),
    (
        "openai-key",
        re.compile(rb"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}\b"),
    ),
    ("anthropic-key", re.compile(rb"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("google-api-key", re.compile(rb"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("github-token", re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
)


def _fingerprint(value: bytes | str) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8", errors="replace")
    return hashlib.sha256(value).hexdigest()[:12]


def _line_number(data: bytes | str, offset: int) -> int:
    newline = b"\n" if isinstance(data, bytes) else "\n"
    return data.count(newline, 0, offset) + 1


def scan_bytes(label: str, data: bytes) -> list[tuple[str, int, str, str]]:
    if len(data) > MAX_TEXT_SIZE or b"\0" in data[:4096]:
        return []

    findings: list[tuple[str, int, str, str]] = []
    for rule, pattern in HIGH_CONFIDENCE_PATTERNS:
        for match in pattern.finditer(data):
            findings.append(
                (label, _line_number(data, match.start()), rule, _fingerprint(match.group(0)))
            )

    text = data.decode("utf-8", errors="ignore")
    for match in LITERAL_CREDENTIAL.finditer(text):
        value = match.group(2).strip()
        if not PLACEHOLDER_VALUE.search(value):
            findings.append(
                (
                    label,
                    _line_number(text, match.start()),
                    "literal-credential",
                    _fingerprint(value),
                )
            )

    for match in URL_PATTERN.finditer(text):
        url = match.group(0).rstrip("),.;]")
        try:
            host = (urlsplit(url).hostname or "").lower()
        except ValueError:
            host = ""
        if host in PLACEHOLDER_HOSTS:
            continue
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        if line_end < 0:
            line_end = len(text)
        context = text[line_start:line_end]
        is_ai_service = any(part in host for part in AI_SERVICE_HOST_PARTS)
        if is_ai_service or PRIVATE_URL_CONTEXT.search(context):
            findings.append(
                (
                    label,
                    _line_number(text, match.start()),
                    "ai-translation-url",
                    _fingerprint(url),
                )
            )
    return findings


def _git_blob_paths(refs: list[str]) -> dict[str, set[str]]:
    command = ["git", "rev-list", "--objects", *refs]
    rows = subprocess.check_output(command).decode("utf-8", errors="replace").splitlines()
    paths: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        oid, separator, path = row.partition(" ")
        if separator:
            paths[oid].add(path)
    return paths


def scan_git_refs(refs: list[str]) -> list[tuple[str, int, str, str]]:
    refs = [ref for ref in refs if ref and ref != ZERO_OID]
    if not refs:
        return []
    paths = _git_blob_paths(refs)
    request = "".join(f"{oid}\n" for oid in paths).encode("ascii")
    batch = subprocess.check_output(["git", "cat-file", "--batch"], input=request)
    cursor = 0
    findings: list[tuple[str, int, str, str]] = []
    for requested_oid in paths:
        header_end = batch.index(b"\n", cursor)
        header = batch[cursor:header_end].decode("ascii", errors="replace")
        cursor = header_end + 1
        fields = header.split()
        if len(fields) != 3:
            continue
        _actual_oid, kind, raw_size = fields
        size = int(raw_size)
        data = batch[cursor : cursor + size]
        cursor += size + 1
        if kind != "blob":
            continue
        label = "git:" + sorted(paths[requested_oid])[0]
        findings.extend(scan_bytes(label, data))
    return findings


def scan_path(path: Path) -> list[tuple[str, int, str, str]]:
    findings: list[tuple[str, int, str, str]] = []
    files = [path] if path.is_file() else path.rglob("*")
    for candidate in files:
        if not candidate.is_file() or ".git" in candidate.parts:
            continue
        try:
            data = candidate.read_bytes()
        except OSError:
            continue
        findings.extend(scan_bytes(f"path:{candidate.as_posix()}", data))
    return findings


def scan_archive(path: Path) -> list[tuple[str, int, str, str]]:
    findings: list[tuple[str, int, str, str]] = []
    with zipfile.ZipFile(path) as archive:
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            findings.extend(scan_bytes(f"zip:{entry.filename}", archive.read(entry)))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", action="append", default=[])
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--archive", action="append", default=[])
    args = parser.parse_args()
    if not (args.ref or args.path or args.archive):
        parser.error("at least one --ref, --path, or --archive is required")

    findings: list[tuple[str, int, str, str]] = []
    findings.extend(scan_git_refs(args.ref))
    for raw_path in args.path:
        findings.extend(scan_path(Path(raw_path)))
    for raw_path in args.archive:
        findings.extend(scan_archive(Path(raw_path)))

    findings = sorted(set(findings))
    if findings:
        print("SECURITY_SCAN_BLOCKED")
        for label, line, rule, fingerprint in findings:
            print(f"{label}:{line}: {rule} sha256={fingerprint}")
        return 1
    print("SECURITY_SCAN_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
