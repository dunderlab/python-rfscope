"""
ScanHackRF Module
=================

This module provides the ScanHackRF class which extends the functionality of
the HackRF class by adding asynchronous frequency scanning capabilities. The
scanning process collects frequency data in specified bands and processes it
using a callback function.

Classes
-------
ScanHackRF
    A subclass of HackRF that adds asynchronous frequency scanning capabilities.
"""

from rfscope.hackrf.core import HackRF
import logging
from typing import Callable


class ScanHackRF(HackRF):
    """"""

    def __init__(self, *args: tuple, **kwargs: dict):
        """
        Initialize the ScanHackRF object.

        This method sets up the ScanHackRF object by initializing the
        superclass and creating an asyncio event for scan completion.

        Parameters
        ----------
        *args : tuple
            Positional arguments to pass to the superclass initialization.
        **kwargs : dict
            Keyword arguments to pass to the superclass initialization.
        """
        super().__init__(*args, **kwargs)
        # self.scan_event = asyncio.Event()

    def scan(
        self,
        bands: list[float],
        sample_rate: float = 20e6,
        step_width: float = 10e6,
        step_offset: float = None,
        read_num_blocks: int = 1,
        buffer_num_blocks: int = 1,
        callback: Callable[[dict], None] = None,
        interleaved: bool = False,
        blocks_per_callback: int = 1,
    ) -> None:
        r"""
        Perform a frequency band sweep scan and process the data asynchronously.

        Parameters
        ----------
        bands : list of float
            List of frequency bands (in Hz) to scan. Each band is represented
            as a tuple of start and end frequencies.
        sample_rate : float, optional
            The sampling rate in Hz. Default is 20e6.
        step_width : float, optional
            The width of each frequency step in Hz. Default is 10e6.
        step_offset : float, optional
            Offset added to each frequency step. If None, defaults to half the
            sample rate.
        read_num_blocks : int, optional
            Number of blocks to read in each step. Default is 1.
        buffer_num_blocks : int, optional
            Number of blocks to store in the buffer. Default is 1.
        callback : callable, optional
            A callback function that processes the scanned frequency data.
            If None, it defaults to the internal `_callback` method.
        interleaved : bool, optional
            If True, enable interleaved sweep mode. Default is False.
        blocks_per_callback: int, optional
            Subsample rate for sweep callback; defines how often _sweep_pipe_function is called.

        Returns
        -------
        None

        Notes
        -----
        This method configures the HackRF device to start a frequency sweep
        scan and waits for an event to signal the end of the scan. The scanned
        data is processed using the specified or default callback function.
        """
        block_size = 16384
        self.sample_rate = sample_rate

        if blocks_per_callback > 1:
            buffer_num_blocks = read_num_blocks * blocks_per_callback

        self.start_sweep(
            bands,
            pipe_function=(self._callback if callback is None else callback),
            step_width=step_width,
            num_bytes=block_size * read_num_blocks,
            step_offset=step_offset,
            interleaved=interleaved,
            buffer_size=block_size * buffer_num_blocks,
            blocks_per_callback=blocks_per_callback,
        )

    def _callback(self, data_freqs: dict[float, list], sweep_config: dict) -> bool:
        """
        Process the frequency data gathered during the sweep scan.

        Parameters
        ----------
        data_freqs : dict[float, list]
            A dictionary where the keys are the center frequencies (in Hz) at which data was collected,
            and the values are lists of data corresponding to those frequencies.
        sweep_config : dict
            A dictionary containing the configuration of the sweep operation.

        Returns
        -------
        bool
            Returns True if the scan_event is set, indicating that the scanning process should stop.

        Notes
        -----
        This is a helper function that is primarily used internally by the `scan` method.
        It logs the number of data values collected for each frequency and checks whether the scan event
        is set to determine if the scanning process should be halted.
        """
        for freq in data_freqs:
            data = data_freqs[freq]
            logging.debug(
                f"The queue for {int(freq / 1e6)} MHz contains {len(data)} values."
            )
        # return self.scan_event.is_set()
