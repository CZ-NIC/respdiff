from argparse import ArgumentParser, Namespace
import logging
import os
import sys

import cfg


LOGGING_LEVEL = logging.DEBUG
CONFIG_FILENAME = 'respdiff.cfg'
REPORT_FILENAME = 'report.json'


def setup_logging(level: int = LOGGING_LEVEL) -> None:
    logging.basicConfig(format='%(asctime)s %(levelname)8s  %(message)s', level=level)


def add_arg_config(parser: ArgumentParser) -> None:
    parser.add_argument('-c', '--config', type=cfg.read_cfg,
                        default=CONFIG_FILENAME, dest='cfg',
                        help='config file (default: {})'.format(CONFIG_FILENAME))


def add_arg_envdir(parser: ArgumentParser) -> None:
    parser.add_argument('envdir', type=str,
                        help='LMDB environment to read/write queries, answers and diffs')


def add_arg_datafile(parser: ArgumentParser) -> None:
    parser.add_argument('-d', '--datafile',
                        help='JSON report file (default: <envdir>/{})'.format(
                            REPORT_FILENAME))


def get_datafile(args: Namespace, check_exists=True) -> str:
    datafile = args.datafile
    if datafile is None:
        datafile = os.path.join(args.envdir, REPORT_FILENAME)

    if check_exists and not os.path.exists(datafile):
        logging.error("JSON report (%s) doesn't exist!", datafile)
        sys.exit(1)

    return datafile
