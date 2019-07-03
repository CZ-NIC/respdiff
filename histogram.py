#!/usr/bin/env python3

# NOTE: Due to a weird bug, numpy is detected as a 3rd party module, while lmdb
#       is not and pylint complains about wrong-import-order.
#       Since these checks have to be disabled for matplotlib imports anyway, they
#       were moved a bit higher up to avoid the issue.
# pylint: disable=wrong-import-order,wrong-import-position
import argparse
import logging
import math
import os
from typing import Dict, List, Tuple, Optional
import sys

import dns
import lmdb
import numpy as np

from respdiff import cfg, cli
from respdiff.database import DNSRepliesFactory, LMDB, MetaDatabase
from respdiff.typing import ResolverID

# Force matplotlib to use a different backend to handle machines without a display
import matplotlib
import matplotlib.ticker as mtick
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa


HISTOGRAM_RCODE_MAX = 23


def load_data(
            txn: lmdb.Transaction,
            dnsreplies_factory: DNSRepliesFactory
        ) -> Dict[ResolverID, List[Tuple[float, Optional[int]]]]:
    data = {}  # type: Dict[ResolverID, List[Tuple[float, Optional[int]]]]
    cursor = txn.cursor()
    for value in cursor.iternext(keys=False, values=True):
        replies = dnsreplies_factory.parse(value)
        for resolver, reply in replies.items():
            message = reply.parse_wire()[0]
            if message:
                rcode = message.rcode()
            else:
                rcode = None
            data.setdefault(resolver, []).append((reply.time, rcode))
    return data


def plot_log_percentile_histogram(
            data: Dict[str, List[float]],
            title: str,
            config=None
        ) -> None:
    """
    For graph explanation, see
    https://blog.powerdns.com/2017/11/02/dns-performance-metrics-the-logarithmic-percentile-histogram/
    """
    plt.rcParams["font.family"] = "monospace"
    _, ax = plt.subplots(figsize=(8, 8))

    # Distribute sample points along logarithmic X axis
    percentiles = np.logspace(-3, 2, num=100)

    ax.set_xscale('log')
    ax.xaxis.set_major_formatter(mtick.FormatStrFormatter('%s'))
    ax.set_yscale('log')
    ax.yaxis.set_major_formatter(mtick.FormatStrFormatter('%s'))

    ax.grid(True, which='major')
    ax.grid(True, which='minor', linestyle='dotted', color='#DDDDDD')

    ax.set_xlabel('Slowest percentile')
    ax.set_ylabel('Response time [ms]')
    ax.set_title('Resolver Response Time' + " - " + title)

    # plot data
    for server in sorted(data):
        if data[server]:
            try:
                color = config[server]['graph_color']
            except KeyError:
                color = None

            # convert to ms and sort
            values = sorted([1000 * x for x in data[server]], reverse=True)
            ax.plot(percentiles,
                    [values[math.ceil(pctl * len(values) / 100) - 1] for pctl in percentiles], lw=2,
                    label='{:<10}'.format(server) + " " + '{:9d}'.format(len(values)), color=color)

    plt.legend()


def create_histogram(
            data: Dict[str, List[float]],
            filename: str,
            title: str,
            config=None
        ) -> None:
    # don't plot graphs which don't contain any finite time
    if any(any(time < float('+inf') for time in d) for d in data.values()):
        plot_log_percentile_histogram(data, title, config)
        # save to file
        plt.savefig(filename, dpi=300)


def histogram_by_rcode(
            data: Dict[ResolverID, List[Tuple[float, Optional[int]]]],
            filename: str,
            title: str,
            config=None,
            rcode: Optional[int] = None
        ) -> None:
    def same_rcode(value: Tuple[float, Optional[int]]) -> bool:
        if rcode is None:
            if value[1] is None:
                return True
            return False
        else:
            return rcode == value[1]

    filtered_by_rcode = {
        resolver: [time for (time, rc) in filter(same_rcode, values)]
        for (resolver, values) in data.items()}
    create_histogram(filtered_by_rcode, filename, title, config)


def main():
    cli.setup_logging()
    parser = argparse.ArgumentParser(
        description='Plot query response time histogram from answers stored '
                    'in LMDB')
    parser.add_argument('-o', '--output', type=str,
                        default='histogram',
                        help='output directory for image files (default: histogram)')
    parser.add_argument('-c', '--config', default='respdiff.cfg', dest='cfgpath',
                        help='config file (default: respdiff.cfg)')
    parser.add_argument('envdir', type=str,
                        help='LMDB environment to read answers from')
    args = parser.parse_args()
    config = cfg.read_cfg(args.cfgpath)
    servers = config['servers']['names']
    dnsreplies_factory = DNSRepliesFactory(servers)

    with LMDB(args.envdir, readonly=True) as lmdb_:
        adb = lmdb_.open_db(LMDB.ANSWERS)

        try:
            MetaDatabase(lmdb_, servers, create=False)  # check version and servers
        except NotImplementedError as exc:
            logging.critical(exc)
            sys.exit(1)

        with lmdb_.env.begin(adb) as txn:
            data = load_data(txn, dnsreplies_factory)

    if not os.path.exists(args.output):
        os.makedirs(args.output)
    filepath = os.path.join(args.output, 'all.png')
    create_histogram({k: [tup[0] for tup in d] for (k, d) in data.items()},
                     filepath, "all", config)

    # rcode-specific queries
    for rcode in range(HISTOGRAM_RCODE_MAX + 1):
        rcode_text = dns.rcode.to_text(rcode)
        filepath = os.path.join(args.output, rcode_text + ".png")
        histogram_by_rcode(data, filepath, rcode_text, config, rcode)
    filepath = os.path.join(args.output, "unparsed.png")
    histogram_by_rcode(data, filepath, "unparsed queries", config, None)


if __name__ == '__main__':
    main()
