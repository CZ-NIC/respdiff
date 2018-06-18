#!/usr/bin/env python3

import argparse
from typing import Optional, Sequence, Union

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


VIOLIN_FIGSIZE = (3, 6)
VIOLIN_COLOR = 'tab:grey'


def plot_violin(
            ax: matplotlib.axes.Axes,
            stats: Stats,
            label: str,
            samples: Optional[Union[float, Sequence[float]]] = None
        ) -> None:
    def draw_hline(y, color, width=0.7):
        xmin = (1 - width) / 2
        xmax = 1 - xmin
        ax.axhline(y, color=color, xmin=xmin, xmax=xmax)

    # turn off axis spines
    for sp in ['right', 'top', 'bottom']:
        ax.spines[sp].set_color('none')
    # move the left ax spine to center
    ax.spines['left'].set_position(('data', 1))

    ax.set_title(label, fontdict={'fontsize': 14})

    # plot graph
    violin_parts = ax.violinplot(stats.sequence, bw_method=0.07,
                                 showmedians=False, showextrema=False)
    for pc in violin_parts['bodies']:
        pc.set_facecolor(VIOLIN_COLOR)
        pc.set_edgecolor(VIOLIN_COLOR)
    draw_hline(stats.min, VIOLIN_COLOR, 0.5)
    draw_hline(stats.median, VIOLIN_COLOR, 0.5)
    draw_hline(stats.max, VIOLIN_COLOR, 0.5)

    cutoff = stats.cutoff
    draw_hline(cutoff, 'tab:orange', 0.9)

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

    # draw line representing sample(s)
    if samples is not None:
        if not isinstance(samples, list):
            samples = [samples]  # type: ignore
        for sample in samples:
            if sample < stats.min:
                color = 'tab:green'
            elif sample <= cutoff:
                color = 'tab:blue'
            else:
                color = 'tab:red'
            draw_hline(sample, color)


def overview_plot(
            sumstats: SummaryStatistics,
            fields: Sequence[FieldLabel],
            samples: Optional[Union[Summary, Sequence[Summary]]] = None,
            label: str = ''
        ) -> None:
    if samples is None:
        samples = []
    elif not isinstance(samples, list):
        samples = [samples]  # type: ignore

    # prepare subplot axis
    fig, axes = plt.subplots(3, 7, figsize=(7*3, 3*6))  # TODO un-hardcode

    def axes_iter(axes):
        index = 0
        while True:
            ix = index // 7
            iy = index % 7
            index += 1
            try:
                yield axes[ix, iy]
            except IndexError:
                return

    ax_it = axes_iter(axes)

    # target disagreements
    assert sumstats.target_disagreements is not None
    plot_violin(
        next(ax_it),
        sumstats.target_disagreements,
        'target_disagreements',
        [len(summary) for summary in samples])

    # TODO remove copypasta
    # upstream unstable
    assert sumstats.upstream_unstable is not None
    plot_violin(
        next(ax_it),
        sumstats.upstream_unstable,
        'upstream_unstable',
        [summary.upstream_unstable for summary in samples])

    # not 100% reproducible
    assert sumstats.not_reproducible is not None
    plot_violin(
        next(ax_it),
        sumstats.not_reproducible,
        'not_reproducible',
        [summary.not_reproducible for summary in samples])

    # fields
    assert sumstats.fields is not None
    fcs = [summary.get_field_counters() for summary in samples]
    for field in fields:
        plot_violin(
            next(ax_it),
            sumstats.fields[field].total,
            field,
            [len(list(fc[field].elements())) for fc in fcs])

    # hide unused axis
    for ax in ax_it:
        ax.set_visible(False)

    # save image
    plt.tight_layout()
    plt.subplots_adjust(top=0.9)
    fig.suptitle('Fields {}'.format(label), fontsize=22)
    plt.savefig('statplot_fields.svg')  # TODO: this forcibly overwrites - .bak + warning
    plt.close()


# TODO plot mismatches
#     # get all kinds of mismatches for field
#     mismatches = []
#     for fc in fcs:
#         mismatches.extend([mismatch for mismatch in fc[field]])
#     mismatches = set(mismatches)
#     for mismatch in mismatches:
#         mdata = [fc[field][mismatch] for fc in fcs]
#         plot_seq(mdata, fstats[str(mismatch.key)].median, fstats[str(mismatch.key)].mad,
#                  '{}_{}'.format(field, mismatch.key))


def main():
    cli.setup_logging()
    # TODO fix this doc + create doc/statcmp.rst
    parser = argparse.ArgumentParser(description='\n'.join([
        "Compare or plot reports against statistical data",
        "",
        "  - comparison: Reports can be checked if the fall within threshold",
        "                defined by the statistics file.",
        "                Exit codes:",
        "                  0: all reports pass, or none were provided",
        "                  1: general error",
        "                  3: some of the reports don't pass",
        "",
        "  - plot: Statistical data is plotted using violin graphs, representing",
        "          the distribution of samples (histogram). Upper threshold is",
        "          represented by orange. If report is provided, its position in",
        "          dataset is represented by blue (within expected bounds),",
        "          red (exceeded threshold) or green (below minimum). Multiple",
        "          reports can be provided.",
        "",
        ]))

    cli.add_arg_stats(parser)
    cli.add_arg_report(parser)
    cli.add_arg_config(parser)
    parser.add_argument('-p', '--plot', choices=['all', 'off', 'fail'], default='all',
                        help="which plots to generate")  # TODO implement

    args = parser.parse_args()
    reports = [report for report in args.report if report is not None]
    summaries = cli.load_summaries(reports)
    sumstats = args.stats
    field_weights = args.cfg['report']['field_weights']

    # TODO what if field is missing in stats?
    overview_plot(sumstats, field_weights, summaries)


if __name__ == '__main__':
    main()
