#!/usr/bin/env python3

import argparse
import sys
from typing import Optional, Sequence

from respdiff import cli
from respdiff.dataformat import Summary
from respdiff.stats import Stats, SummaryStatistics
from respdiff.typing import FieldLabel

# pylint: disable=wrong-import-order,wrong-import-position
import matplotlib
import matplotlib.axes
import matplotlib.ticker as ticker
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa


COLOR_OK = 'tab:blue'
COLOR_GOOD = 'tab:green'
COLOR_BAD = 'xkcd:bright red'
COLOR_BOUNDARY = 'tab:orange'
COLOR_BG = 'tab:gray'
COLOR_LABEL = 'black'

VIOLIN_FIGSIZE = (3, 6)


def violin_plot(
            ax: matplotlib.axes.Axes,
            stats: Stats,
            label: str,
            samples: Optional[Sequence[float]] = None
        ) -> bool:
    def draw_hline(y, color, width=0.7):
        xmin = (1 - width) / 2
        xmax = 1 - xmin
        ax.axhline(y, color=color, xmin=xmin, xmax=xmax)

    below_min = False
    above_max = False

    if samples is not None:
        below_min = any(sample < stats.min for sample in samples)
        above_max = any(sample > stats.max for sample in samples)

        # draw line representing sample(s)
        for sample in samples:
            if sample < stats.min:
                color = COLOR_GOOD
                below_min = True
            elif sample <= stats.upper_boundary:
                color = COLOR_OK
            else:
                color = COLOR_BAD
                above_max = True
            draw_hline(sample, color)

    # draw colored title
    if above_max:
        color = COLOR_BAD
    elif below_min:
        color = COLOR_GOOD
    else:
        color = COLOR_LABEL
    ax.set_title(label, fontdict={'fontsize': 14}, color=color)

    # turn off axis spines
    for sp in ['right', 'top', 'bottom']:
        ax.spines[sp].set_color('none')
    # move the left ax spine to center
    ax.spines['left'].set_position(('data', 1))

    # plot graph
    violin_parts = ax.violinplot(stats.sequence, bw_method=0.07,
                                 showmedians=False, showextrema=False)
    for pc in violin_parts['bodies']:
        pc.set_facecolor(COLOR_BG)
        pc.set_edgecolor(COLOR_BG)
    draw_hline(stats.min, COLOR_BG, 0.5)
    draw_hline(stats.median, COLOR_BG, 0.5)
    draw_hline(stats.max, COLOR_BG, 0.5)
    draw_hline(stats.upper_boundary, COLOR_BOUNDARY, 0.9)

    # customize axis ticks
    ax.xaxis.set_major_locator(ticker.NullLocator())
    ax.xaxis.set_minor_locator(ticker.NullLocator())
    if max(stats.sequence) == 0:
        ax.yaxis.set_major_locator(ticker.FixedLocator([0]))
    else:
        ax.yaxis.set_major_locator(ticker.MaxNLocator(
            nbins='auto', steps=[1, 2, 4, 5, 10], integer=True))
    ax.yaxis.set_minor_locator(ticker.NullLocator())
    ax.tick_params(labelsize=14)

    return not above_max


def _axes_iter(axes, width: int):
    index = 0
    while True:
        ix = index // width
        iy = index % width
        index += 1
        try:
            yield axes[ix, iy]
        except IndexError:
            return


def overview_plot(
            sumstats: SummaryStatistics,
            fields: Sequence[FieldLabel],
            samples: Optional[Sequence[Summary]] = None,
            label: str = 'fields_overview'
        ) -> bool:
    if samples is None:
        samples = []

    passed = True
    OVERVIEW_X_FIG = 7
    OVERVIEW_Y_FIG = 3

    # prepare subplot axis
    fig, axes = plt.subplots(
        OVERVIEW_Y_FIG,
        OVERVIEW_X_FIG,
        figsize=(OVERVIEW_X_FIG*VIOLIN_FIGSIZE[0], OVERVIEW_Y_FIG*VIOLIN_FIGSIZE[1]))
    ax_it = _axes_iter(axes, OVERVIEW_X_FIG)

    # target disagreements
    assert sumstats.target_disagreements is not None
    passed &= violin_plot(
        next(ax_it),
        sumstats.target_disagreements,
        'target_disagreements',
        [len(summary) for summary in samples])

    # upstream unstable
    assert sumstats.upstream_unstable is not None
    passed &= violin_plot(
        next(ax_it),
        sumstats.upstream_unstable,
        'upstream_unstable',
        [summary.upstream_unstable for summary in samples])

    # not 100% reproducible
    assert sumstats.not_reproducible is not None
    passed &= violin_plot(
        next(ax_it),
        sumstats.not_reproducible,
        'not_reproducible',
        [summary.not_reproducible for summary in samples])

    # fields
    assert sumstats.fields is not None
    fcs = [summary.get_field_counters() for summary in samples]
    for field in fields:
        passed &= violin_plot(
            next(ax_it),
            sumstats.fields[field].total,
            field,
            [len(list(fc[field].elements())) for fc in fcs])

    # hide unused axis
    for ax in ax_it:
        ax.set_visible(False)

    # display sample size
    fig.text(
        0.95, 0.95,
        'stat sample size: {}'.format(len(sumstats.target_disagreements.sequence)),
        fontsize=18, color=COLOR_BG, ha='right', va='bottom', alpha=0.7)

    # save image
    plt.tight_layout()
    plt.subplots_adjust(top=0.9)
    fig.suptitle(label, fontsize=22)
    plt.savefig('{}.svg'.format(label))
    plt.close()

    return passed


def main():
    cli.setup_logging()
    parser = argparse.ArgumentParser(
        description=("Plot and compare reports against statistical data. "
                     "Returns non-zero exit code if any upper threshold is exceeded."))

    cli.add_arg_stats(parser)
    cli.add_arg_report(parser)
    cli.add_arg_config(parser)
    parser.add_argument('-l', '--label', default='fields_overview',
                        help='Set plot label. It is also used for the filename.')

    args = parser.parse_args()
    reports = [report for report in args.report if report is not None]
    summaries = cli.load_summaries(reports)
    sumstats = args.stats
    field_weights = args.cfg['report']['field_weights']

    passed = overview_plot(sumstats, field_weights, summaries, args.label)

    if not passed:
        sys.exit(3)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
