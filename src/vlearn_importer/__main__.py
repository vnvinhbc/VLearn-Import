"""Command line entrypoint for local checks and systemd."""

import argparse
import logging
import sys
from pathlib import Path

from vlearn_importer.config import Settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VLearn Importer")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="Validate worker configuration")
    subparsers.add_parser("worker", help="Run the systemd worker")
    extract_parser = subparsers.add_parser("extract", help="Extract DOCX/PDF text locally")
    extract_parser.add_argument("path", type=Path)
    extract_parser.add_argument("--output", type=Path, help="Write extracted UTF-8 text here")
    template_parser = subparsers.add_parser("templates", help="Generate example import templates")
    template_parser.add_argument("--output", required=True, type=Path)
    parse_parser = subparsers.add_parser("parse", help="Read a CSV, XLSX or DOCX import template")
    parse_parser.add_argument("path", type=Path)
    parse_parser.add_argument("--kind", required=True)
    args = parser.parse_args(argv)

    if args.command == "templates":
        from vlearn_importer.templates import generate_templates

        generate_templates(args.output)
        return 0

    if args.command == "parse":
        from vlearn_importer.structured import MAX_FILE_BYTES, ParseError, json_bytes, parse_bytes

        try:
            with args.path.open("rb") as stream:
                source = stream.read(MAX_FILE_BYTES + 1)
            rows = parse_bytes(source, args.path.suffix, args.kind)
        except OSError:
            parser.error("Không thể mở tệp mẫu.")
        except ParseError as error:
            parser.error(str(error))
        print(json_bytes({"rows": rows}).decode("utf-8"))
        return 0

    if args.command == "extract":
        from vlearn_importer.extractors.text import extract_text

        text = extract_text(args.path)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
            print(f"Extracted {len(text)} characters to {args.output}")
        else:
            print(text)
        return 0

    try:
        settings = Settings.from_environment()
    except ValueError as error:
        parser.error(str(error))
    if args.command == "check":
        print(f"VLearn importer OK; mode={settings.mode}")
        return 0
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    from vlearn_importer.worker import run_worker

    run_worker(settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
