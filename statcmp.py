#!/usr/bin/env python3

import argparse
import logging
import sys
from typing import Optional, Sequence

from respdiff import cli
from respdiff.dataformat import Summary
from respdiff.stats import Stats, SummaryStatistics
from respdiff.typing import FieldLabel

# pylint: disable=wrong-import-order,wrong-import-position
import matplotlib
import matplotlib.axes
import matplotlib.ticker

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa


COLOR_OK = "tab:blue"
COLOR_GOOD = "tab:green"
COLOR_BAD = "xkcd:bright red"
COLOR_THRESHOLD = "tab:orange"
COLOR_BG = "tab:gray"
COLOR_LABEL = "black"

VIOLIN_FIGSIZE = (3, 6)

SAMPLE_COLORS = {
    Stats.SamplePosition.ABOVE_REF: COLOR_BAD,
    Stats.SamplePosition.ABOVE_THRESHOLD: COLOR_BAD,
    Stats.SamplePosition.NORMAL: COLOR_OK,
    Stats.SamplePosition.BELOW_REF: COLOR_GOOD,
}


class AxisMarker:
    def __init__(
        self, position: float, width: float = 0.7, color: str = COLOR_BG
    ) -> None:
        self.position = position
        self.width = width
        self.color = color

    def draw(self, ax: matplotlib.axes.Axes):
        xmin = (1 - self.width) / 2
        xmax = 1 - xmin
        ax.axhline(self.position, color=self.color, xmin=xmin, xmax=xmax)


def plot_violin(
    ax: matplotlib.axes.Axes,
    violin_data: Sequence[float],
    markers: Sequence[AxisMarker],
    label: str,
    color: str = COLOR_LABEL,
) -> None:
    ax.set_title(label, fontdict={"fontsize": 14}, color=color)

    # plot violin graph
    violin_parts = ax.violinplot(
        violin_data, bw_method=0.07, showmedians=False, showextrema=False
    )
    # set violin background color
    for pc in violin_parts["bodies"]:
        pc.set_facecolor(COLOR_BG)
        pc.set_edgecolor(COLOR_BG)

    # draw axis markers
    for marker in markers:
        marker.draw(ax)

    # turn off axis spines
    for sp in ["right", "top", "bottom"]:
        ax.spines[sp].set_color("none")
    # move the left ax spine to center
    ax.spines["left"].set_position(("data", 1))

    # customize axis ticks
    ax.xaxis.set_major_locator(matplotlib.ticker.NullLocator())
    ax.xaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    if max(violin_data) == 0:  # fix tick at 0 when there's no data
        ax.yaxis.set_major_locator(matplotlib.ticker.FixedLocator([0]))
    else:
        ax.yaxis.set_major_locator(
            matplotlib.ticker.MaxNLocator(
                nbins="auto", steps=[1, 2, 4, 5, 10], integer=True
            )
        )
    ax.yaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    ax.tick_params(labelsize=14)


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


def eval_and_plot_single(
    ax: matplotlib.axes.Axes, stats: Stats, label: str, samples: Sequence[float]
) -> bool:
    markers = []
    below_min = False
    above_thr = False
    for sample in samples:
        result = stats.evaluate_sample(sample)
        markers.append(AxisMarker(sample, color=SAMPLE_COLORS[result]))
        if result in (
            Stats.SamplePosition.ABOVE_REF,
            Stats.SamplePosition.ABOVE_THRESHOLD,
        ):
            above_thr = True
            logging.error(
                "  %s: threshold exceeded! sample: %d / %4.2f%% vs threshold: %d / %4.2f%%",
                label,
                sample,
                stats.get_percentile_rank(sample),
                stats.threshold,
                stats.get_percentile_rank(stats.threshold),
            )
        elif result == Stats.SamplePosition.BELOW_REF:
            below_min = True
            logging.info(
                "  %s: new minimum found! new: %d vs prev: %d", label, sample, stats.min
            )
        else:
            logging.info(
                "  %s: ok! sample: %d / %4.2f%% vs threshold: %d / %4.2f%%",
                label,
                sample,
                stats.get_percentile_rank(sample),
                stats.threshold,
                stats.get_percentile_rank(stats.threshold),
            )

    # add min/med/max markers
    markers.append(AxisMarker(stats.min, 0.5, COLOR_BG))
    markers.append(AxisMarker(stats.median, 0.5, COLOR_BG))
    markers.append(AxisMarker(stats.max, 0.5, COLOR_BG))
    markers.append(AxisMarker(stats.threshold, 0.9, COLOR_THRESHOLD))

    # select label color
    if above_thr:
        color = COLOR_BAD
    elif below_min:
        color = COLOR_GOOD
    else:
        color = COLOR_LABEL

    plot_violin(ax, stats.samples, markers, label, color)

    return not above_thr


def plot_overview(
    sumstats: SummaryStatistics,
    fields: Sequence[FieldLabel],
    summaries: Optional[Sequence[Summary]] = None,
    label: str = "fields_overview",
) -> bool:
    """
    Plot an overview of all fields using violing graphs. If any summaries are provided,
    they are drawn in the graphs and also evaluated. If any sample in any field exceeds
    the threshold, the function return False. True is returned otherwise.
    """
    if summaries is None:
        summaries = []

    passed = True
    OVERVIEW_X_FIG = 7
    OVERVIEW_Y_FIG = 3

    # prepare subplot axis
    fig, axes = plt.subplots(
        OVERVIEW_Y_FIG,
        OVERVIEW_X_FIG,
        figsize=(
            OVERVIEW_X_FIG * VIOLIN_FIGSIZE[0],
            OVERVIEW_Y_FIG * VIOLIN_FIGSIZE[1],
        ),
    )
    ax_it = _axes_iter(axes, OVERVIEW_X_FIG)

    # target disagreements
    assert sumstats.target_disagreements is not None
    samples = [len(summary) for summary in summaries]
    passed &= eval_and_plot_single(
        next(ax_it), sumstats.target_disagreements, "target_disagreements", samples
    )

    # upstream unstable
    assert sumstats.upstream_unstable is not None
    samples = [summary.upstream_unstable for summary in summaries]
    passed &= eval_and_plot_single(
        next(ax_it), sumstats.upstream_unstable, "upstream_unstable", samples
    )

    # not 100% reproducible
    assert sumstats.not_reproducible is not None
    samples = [summary.not_reproducible for summary in summaries]
    passed &= eval_and_plot_single(
        next(ax_it), sumstats.not_reproducible, "not_reproducible", samples
    )

    # fields
    assert sumstats.fields is not None
    fcs = [summary.get_field_counters() for summary in summaries]
    for field in fields:
        if field not in sumstats.fields:
            logging.warning('Field "%s" missing in statistics, omitting...', field)
            continue
        passed &= eval_and_plot_single(
            next(ax_it),
            sumstats.fields[field].total,
            field,
            [len(list(fc[field].elements())) for fc in fcs],
        )

    # hide unused axis
    for ax in ax_it:
        ax.set_visible(False)

    # display sample size
    fig.text(
        0.95,
        0.95,
        "stat sample size: {}".format(len(sumstats.target_disagreements.samples)),
        fontsize=18,
        color=COLOR_BG,
        ha="right",
        va="bottom",
        alpha=0.7,
    )

    # save image
    plt.tight_layout()
    plt.subplots_adjust(top=0.9)
    fig.suptitle(label, fontsize=22)
    plt.savefig("{}.png".format(label))
    plt.close()

    return passed


def main():
    cli.setup_logging()
    parser = argparse.ArgumentParser(
        description=(
            "Plot and compare reports against statistical data. "
            "Returns non-zero exit code if any threshold is exceeded."
        )
    )

    cli.add_arg_stats(parser)
    cli.add_arg_report(parser)
    cli.add_arg_config(parser)
    parser.add_argument(
        "-l",
        "--label",
        default="fields_overview",
        help="Set plot label. It is also used for the filename.",
    )

    args = parser.parse_args()
    sumstats = args.stats
    field_weights = args.cfg["report"]["field_weights"]

    try:
        summaries = cli.load_summaries(args.report)
    except ValueError:
        sys.exit(1)

    logging.info("Start Comparison: %s", args.label)
    passed = plot_overview(sumstats, field_weights, summaries, args.label)

    if not passed:
        sys.exit(3)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
