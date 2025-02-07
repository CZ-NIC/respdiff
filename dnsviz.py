#!/usr/bin/python3
import argparse
import logging
import subprocess
import sys

from respdiff import cli
import respdiff.dnsviz


def main():
    cli.setup_logging()
    parser = argparse.ArgumentParser(
        description="use dnsviz to categorize domains (perfect, warnings, errors)"
    )
    cli.add_arg_config(parser)
    cli.add_arg_dnsviz(parser)
    parser.add_argument(
        "input", type=str, help="input file with domains (one qname per line)"
    )
    args = parser.parse_args()

    njobs = args.cfg["sendrecv"]["jobs"]
    try:
        probe = subprocess.run(
            [
                "dnsviz",
                "probe",
                "-A",
                "-R",
                respdiff.dnsviz.TYPES,
                "-f",
                args.input,
                "-t",
                str(njobs),
            ],
            check=True,
            stdout=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        logging.critical("dnsviz probe failed: %s", exc)
        sys.exit(1)
    except FileNotFoundError:
        logging.critical("'dnsviz' tool is not installed!")
        sys.exit(1)

    try:
        subprocess.run(
            ["dnsviz", "grok", "-o", args.dnsviz],
            input=probe.stdout,
            check=True,
            stdout=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        logging.critical("dnsviz grok failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
