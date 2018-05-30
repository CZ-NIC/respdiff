#!/usr/bin/env python3

# NOTE: Due to a weird bug, numpy is detected as a 3rd party module, while lmdb
#       is not and pylint complains about wrong-import-order.
#       Since these checks have to be disabled for matplotlib imports anyway, they
#       were moved a bit higher up to avoid the issue.
# pylint: disable=wrong-import-order,wrong-import-position
import argparse
import logging
import math
from typing import Dict, List
import sys

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


def load_data(
            txn: lmdb.Transaction,
            dnsreplies_factory: DNSRepliesFactory
        ) -> Dict[ResolverID, List[float]]:
    data = {}  # type: Dict[ResolverID, List[float]]
    cursor = txn.cursor()
    for value in cursor.iternext(keys=False, values=True):
        replies = dnsreplies_factory.parse(value)
        for resolver, reply in replies.items():
            data.setdefault(resolver, []).append(reply.time)
    return data


def plot_log_percentile_histogram(data: Dict[str, List[float]], config=None):
    """
    For graph explanation, see
    https://blog.powerdns.com/2017/11/02/dns-performance-metrics-the-logarithmic-percentile-histogram/
    """
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
    ax.set_title('Resolver Response Time')

    # plot data
    for server in sorted(data):
        try:
            color = config[server]['graph_color']
        except KeyError:
            color = None

        # convert to ms and sort
        values = sorted([1000 * x for x in data[server]], reverse=True)
        ax.plot(percentiles,
                [values[math.ceil(pctl * len(values) / 100) - 1] for pctl in percentiles],
                lw=2, label=server, color=color)

    plt.legend()


def main():
    cli.setup_logging()
    parser = argparse.ArgumentParser(
        description='Plot query response time histogram from answers stored '
                    'in LMDB')
    parser.add_argument('-o', '--output', type=str,
                        default='histogram.svg',
                        help='output image file (default: histogram.svg)')
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
    plot_log_percentile_histogram(data, config)

    # save to file
    plt.savefig(args.output, dpi=300)


if __name__ == '__main__':
    main()
