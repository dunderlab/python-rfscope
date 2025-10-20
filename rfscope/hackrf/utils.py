from matplotlib import pyplot as plt
import subprocess
import os


def preview_scan(
    bands: list[float],
    sample_rate: float = 20e6,
    step_width: float = 10e6,
    step_offset: float = None,
    # read_num_blocks: int = 1,
    # buffer_num_blocks: int = 1,
    # callback: Callable[[dict], None] = None,
    # interleaved: bool = False,
    top=0.5,
    save=None,
    *args,
    **kwargs,
) -> None:

    plt.figure(figsize=(16, 7), dpi=90)

    level = 0
    level_i = 0.05
    for i, [start, end] in enumerate(bands):

        start = start * 1e6
        end = end * 1e6

        if step_offset is None:
            step_offset = sample_rate / 2

        scan = start - step_offset

        plt.fill_between(
            [start, end],
            [-0.05, -0.05],
            [top, top],
            color=f'C{i}',
            alpha=0.1,
        )

        plt.vlines(
            start, -0.05, top, color=f'C{i}', linestyle='--', alpha=0.3
        )

        plt.vlines(end, -0.05, top, color=f'C{i}', linestyle='--', alpha=0.3)

        plt.text(start, -0.1, f'{start/1e6:.0f} MHz', ha='center')
        plt.text(end, -0.1, f'{end/1e6:.0f} MHz', ha='center')

        while scan < end:
            plt.fill_between(
                [scan, scan + sample_rate],
                [level, level],
                [level + level_i, level + level_i],
                color=f'C{i}',
                alpha=0.5,
            )

            plt.text(
                scan + sample_rate,
                level - 0.025,
                f'{(scan+sample_rate)/1e6:.0f} MHz',
                ha='center',
                color=f'C{i}',
            )

            scan += step_width
            level += 0.05

        level = 0

    plt.axis('off')

    if save:
        plt.savefig(save)

    return plt.gca()



def load_lib():
    """"""
    os.environ['LD_LIBRARY_PATH'] = '/usr/local/lib:' + os.environ.get(
        'LD_LIBRARY_PATH', ''
    )
    subprocess.run(['ldconfig'], check=True)
