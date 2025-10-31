"""
HackRF module for interfacing with HackRF software-defined radio (SDR) hardware.

This module provides a comprehensive interface for managing and operating HackRF devices.
It includes functionalities for receiving and transmitting signals, setting device parameters,
handling errors, and enabling various operational modes.

Key Functionalities
--------------------
- Enumerate connected HackRF devices.
- Open and close the HackRF device for communication.
- Start and stop data reception with optional processing.
- Start and stop data transmission.
- Retrieve and set parameters such as frequency, sample rate, and gain.

"""

from ctypes import *
from collections.abc import Callable
from .cinterface import (
    libhackrf,
    p_hackrf_device,
    TransceiverMode,
    lib_hackrf_transfer,
    lib_read_partid_serialno_t,
    ERRORS,
    BASEBAND_FILTER_VALID_VALUES,
)
import struct
from collections import deque


# Attempt to import numpy for efficient numerical computations. If the import fails,
# set numpy to None to handle cases where numpy is not available.
try:
    import numpy as np
except ImportError:
    np = None


class HackRF(object):
    """
    HackRF class for interfacing with the HackRF software-defined radio (SDR) hardware.

    This class provides a high-level interface for controlling and obtaining data from
    the HackRF device. It facilitates both reception and transmission of signals by managing
    the device's settings, including frequency, sampling rate, gain, and various operational modes.

    Key Functionalities
    --------------------
    - Enumerate connected HackRF devices.
    - Open and close the HackRF device for communication.
    - Start and stop receiving data with optional data processing.
    - Start and stop transmitting data.
    - Retrieve and set device parameters such as frequency, sample rate, and gain.

    Usage Example
    -------------
    To use the HackRF class:

    >>> hackrf = HackRF()
    >>> hackrf.center_freq = 915e6  # Set frequency to 915 MHz
    >>> hackrf.start_rx()  # Start receiving data
    >>> data = hackrf.read_samples(1024)  # Read 1024 samples
    >>> hackrf.stop_rx()  # Stop receiving data
    >>> hackrf.close()  # Close the device

    Attributes
    ----------
    _center_freq : int
        The current center frequency in Hz.
    _sample_rate : int
        The current sample rate in Hz.
    _filter_bandwidth : int
        The current baseband filter bandwidth.
    _amplifier_on : bool
        Indicates if the RF amplifier is enabled.
    _bias_tee_on : bool
        Indicates if the bias tee is enabled.
    _lna_gain : int
        Gain setting for the low noise amplifier.
    _vga_gain : int
        Gain setting for the variable gain amplifier.
    _txvga_gain : int
        Gain setting for the transmit variable gain amplifier.
    _device_opened : bool
        State indicating if the device is open.
    _device_pointer : p_hackrf_device
        Pointer to the HackRF device.
    _transceiver_mode : TransceiverMode
        Current operational mode of the HackRF transceiver.
    _rx_pipe_function : Callable[[bytes], int]
        Function to process incoming data during receiving.
    _sweep_pipe_function : Callable[[dict], int]
        Function to process incoming data during frequency sweeps.
    _sample_count : int
        Counter for the number of samples processed.
    _sample_count_limit : int
        Limit for the number of samples to collect.
    buffer : bytearray
        Buffer to store the collected samples.
    """

    _center_freq: int = 100e6
    _sample_rate: int = 20e6
    _filter_bandwidth: int
    _amplifier_on: bool = False
    _bias_tee_on: bool = False
    _lna_gain: int = 16
    _vga_gain: int = 16
    _txvga_gain: int = 10
    _device_opened = False
    _device_pointer: p_hackrf_device = p_hackrf_device(None)
    _transceiver_mode: TransceiverMode = TransceiverMode.HACKRF_TRANSCEIVER_MODE_OFF
    # function that will be called on incoming data. Argument is data bytes.
    # return value True means that we need to stop data acquisiton
    _rx_pipe_function: Callable[[bytes], int] = None
    # function that will be called on incoming data during sweep. Argument is dict like {center_freq1: bytes1, center_freq2: bytes2, ...}
    # return value True means that we need to stop data acquisiton
    _sweep_pipe_function: Callable[[dict], int] = None
    # counts samples that already have been stored or transferred to pipe function
    _sample_count: int = 0
    # set limit of samples to be stored or transferred to pipe function
    _sample_count_limit: int = 0
    # data collected in rx mode
    buffer: bytearray()
    # subsample rate for sweep callback; defines how often _sweep_pipe_function is called
    _blocks_per_callback: int = 1
    _callback_counter: int = 0

    @staticmethod
    def enumerate() -> list[str]:
        """
        Enumerate HackRF devices connected to the host.

        This method returns a list of serial numbers corresponding to the HackRF devices
        connected to the system. Each serial number is provided as a string.

        Returns
        -------
        list[str]
            A list of serial numbers of connected HackRF devices.

        Raises
        ------
        RuntimeError
            If there is an error communicating with the HackRF library while fetching the
            device list.

        Notes
        -----
        Ensure that the HackRF devices are properly connected and recognized by the system
        before calling this method. The returned list will be empty if no devices are found.

        See Also
        --------
        HackRF.__init__ : For initializing a HackRF device.
        """
        r = libhackrf.hackrf_device_list()
        count = r.contents.devicecount
        return [s.decode("utf-8") for s in r.contents.serial_numbers[:count]]

    def _check_error(self, code: int) -> None:
        """
        Check for errors returned by the HackRF library calls.

        This method checks the error code returned by the HackRF library functions,
        handling specific error cases and raising appropriate exceptions. It ensures
        that the device state remains consistent even in case of an error.

        Parameters
        ----------
        code : int
            The error code returned by a HackRF API function call.

        Raises
        ------
        RuntimeError
            If the error code indicates a failure.

        Notes
        -----
        The method automatically disables the bias tee and sets the transceiver mode to OFF
        when an error is detected. It's important to handle errors properly to prevent resource
        leaks or unexpected behaviors during operation.
        """
        if code == 0 or code == -1004 or code == 1:
            return
        self._transceiver_mode = TransceiverMode.HACKRF_TRANSCEIVER_MODE_OFF
        self._bias_tee_on = False
        self.close()
        raise RuntimeError(
            ERRORS.get(code, f"libhackrf returned unknown error code {code}")
        )

    def __init__(self, device_index: int = 0) -> None:
        """
        Initialize an instance of the HackRF device.

        This constructor initializes the HackRF device corresponding to the
        specified `device_index`, which can be obtained from the
        `enumerate()` method. It automatically opens the device and sets
        parameters to their safe defaults.

        Parameters
        ----------
        device_index : int, optional
            The index of the device to open. Defaults to 0, which refers to
            the first HackRF device detected.

        Raises
        ------
        RuntimeError
            If there is an error while trying to open the device.

        Notes
        -----
        Make sure to call `close()` method when communication is no longer
        required to free resources.
        """
        self.open(device_index)

        self.amplifier_on = False
        self.bias_tee = False
        self.lna_gain = 16
        self.vga_gain = 16
        self.txvga_gain = 10
        self.center_freq = 433.2e6
        self.sample_rate = 20e6
        # we need to keep these values in memory constantly because Python garbage collector tends to
        # delete them when they go out of scope, and we get segfaults in C library
        self._cfunc_rx_callback = CFUNCTYPE(c_int, POINTER(lib_hackrf_transfer))(
            self._rx_callback
        )
        self._cfunc_sweep_callback = CFUNCTYPE(c_int, POINTER(lib_hackrf_transfer))(
            self._sweep_callback
        )
        self._cfunc_tx_callback = CFUNCTYPE(c_int, POINTER(lib_hackrf_transfer))(
            self._tx_callback
        )
        self._rx_pipe_function = None

    def open(self, device_index: int = 0) -> None:
        """
        Open the HackRF device for communication.

        This method initializes the device with the given index, allowing interaction
        with the HackRF through the provided `libhackrf` interface. The device must be
        available and connected to the host system.

        Parameters
        ----------
        device_index : int, optional
            The index of the device to open, corresponding to the order in
            which devices are enumerated. The default value is 0, which refers
            to the first HackRF device detected.

        Raises
        ------
        ValueError
            If the specified device index exceeds the number of connected HackRF devices
            or if there are no HackRF devices attached.
        RuntimeError
            If there is an error while trying to open the device.

        Notes
        -----
        This method should be called before any data transmission or reception is
        attempted. Be sure to close the device using the `close()` method when
        communication is no longer required.

        See Also
        --------
        close : Method to close the device communication.
        """
        hdl = libhackrf.hackrf_device_list()
        if device_index >= hdl.contents.devicecount:
            raise (
                ValueError(
                    f"HackRF with index {device_index} not attached to host (found {hdl.contents.devicecount} HackRF devices)"
                )
                if hdl.contents.devicecount
                else ValueError("No HackRF devices attached to host")
            )
        self._check_error(
            libhackrf.hackrf_device_list_open(
                hdl, device_index, pointer(self._device_pointer)
            )
        )
        self._device_opened = True

    def close(self) -> None:
        """
        Close device communications.

        This method terminates communication with the HackRF device. If the device is already closed, this method does nothing.

        Notes
        -----
        - It is important to close the device properly to free up resources and avoid potential issues when attempting to reopen it.
        - This method should be called before the object is destroyed to ensure clean resource management.

        Raises
        ------
        RuntimeError
            If there is an error while trying to close the device.
        """
        if not self._device_opened:
            return

        libhackrf.hackrf_close(self._device_pointer)
        self.device_opened = False

    def __del__(self) -> None:
        """
        Clean up resources before the object is destroyed.

        This method ensures that all resources are properly released
        and that any necessary shutdown procedures are followed
        to avoid resource leaks. It will be automatically called
        when the object is about to be destroyed.

        Notes
        -----
        - Make sure to call the `close()` method to terminate any
          ongoing communications with the HackRF device before
          the object is destroyed.

        Raises
        ------
        RuntimeError
            If there is an error during the cleanup process.
        """
        self.close()

    def _rx_callback(self, hackrf_transfer: lib_hackrf_transfer) -> int:
        """
        Callback function for handling the incoming data packets during receive operation.

        This callback function is responsible for populating the buffer with the received samples.
        Once the buffer reaches the sample count limit or the pipe function returns True,
        the callback function will signal the end of data acquisition.

        Parameters
        ----------
        hackrf_transfer : lib_hackrf_transfer
            A structure containing the buffer and transfer-related information.

        Returns
        -------
        int
            Returns 1 when the data acquisition is complete, otherwise returns 0 to continue receiving data.
        """
        bytes = bytearray(
            cast(
                hackrf_transfer.contents.buffer,
                POINTER(c_byte * hackrf_transfer.contents.buffer_length),
            ).contents
        )
        stop_acquisition = False
        if (
            self._sample_count_limit
            and len(bytes) + self._sample_count >= self._sample_count_limit
        ):
            bytes = bytes[: self._sample_count_limit - self._sample_count]
            stop_acquisition = True
        self._sample_count += len(bytes)
        if self._rx_pipe_function is not None:
            if self._rx_pipe_function(bytes):
                stop_acquisition = True
        else:
            self.buffer += bytes
        if stop_acquisition:
            self._transceiver_mode = TransceiverMode.HACKRF_TRANSCEIVER_MODE_OFF
            self._bias_tee_on = False
            return 1
        return 0

    def start_rx(self, pipe_function: Callable[[bytes], bool] = None) -> None:
        """
        Start receiving data.

        This method initializes the data reception process from the HackRF device.
        It will collect up to `sample_count_limit` bytes of data, storing them
        in an internal buffer or processing them with a specified pipe function.

        Parameters
        ----------
        pipe_function : Callable[[bytes], bool], optional
            A function that processes incoming data bytes. The function should
            return True if data acquisition should stop. If not specified, data
            will be collected in a buffer until `stop_rx()` is called.

        Notes
        -----
        - If `sample_count_limit` is set to zero, the user must explicitly stop
          data acquisition by calling `stop_rx()`.
        - The data collection and storage method varies depending on whether a
          `pipe_function` is provided.

        Raises
        ------
        RuntimeError
            If there is an error starting the reception on the device.

        See Also
        --------
        stop_rx : Method to stop receiving data.
        read_samples : Method to synchronously read a predefined number of samples.
        """
        self.buffer = bytearray()
        self._rx_pipe_function = pipe_function
        self._sample_count = 0
        self._transceiver_mode = TransceiverMode.HACKRF_TRANSCEIVER_MODE_RECEIVE
        self._check_error(
            libhackrf.hackrf_start_rx(
                self._device_pointer,
                self._cfunc_rx_callback,
                None,
            )
        )

    def stop_rx(self) -> None:
        """
        Stop receiving data.

        This method stops the data reception that was started by the `start_rx()` method.
        It can also be used to stop any ongoing reception initiated by other methods
        under multithreading or multiprocessing conditions.

        Notes
        -----
        - This method sets the transceiver mode to `TransceiverMode.HACKRF_TRANSCEIVER_MODE_OFF`.
        - The bias tee will be disabled when this method is called.

        Raises
        ------
        RuntimeError
            If there is an error stopping the reception on the device.

        See Also
        --------
        start_rx : Method to start receiving data.
        read_samples : Method to synchronously read a predefined number of samples.
        """
        self._transceiver_mode = TransceiverMode.HACKRF_TRANSCEIVER_MODE_OFF
        self._bias_tee_on = False
        self._check_error(libhackrf.hackrf_stop_rx(self._device_pointer))

    def read_samples(self, num_samples: int = 131072) -> list[complex] | np.ndarray:
        """
        Synchronous function to read a predefined number of samples into buffer and return them as a numpy array.

        This method captures the specified number of samples from the HackRF device, stores them
        into a buffer, and then retrieves them as a numpy array if the numpy library is available.
        If numpy is not available, it returns the samples as a list of complex numbers.

        Parameters
        ----------
        num_samples : int, optional
            The number of samples to read from the device. Default is 131072.
            If set to 0, the function will return an empty list or array.

        Returns
        -------
        list of complex or np.ndarray
            The captured samples as a list of complex numbers if numpy is not available.
            If numpy is available, returns an ndarray of complex numbers.

        Notes
        -----
        The method sets an internal sample count limit to twice the requested number
        of samples (since each sample includes I and Q components).

        See Also
        --------
        start_rx : Method to start receiving data.
        stop_rx : Method to stop receiving data.
        get_iq : Method to convert raw byte buffer to IQ samples.
        """
        # prevent running forever
        if not num_samples:
            if np:
                return np.array([])
            else:
                return []

        self._sample_count_limit = int(2 * num_samples)
        self.start_rx()

        while self._transceiver_mode != TransceiverMode.HACKRF_TRANSCEIVER_MODE_OFF:
            pass
        self.stop_rx()

        # convert samples to iq
        return self.get_iq(self.buffer)

    def get_iq(self, buffer: bytearray) -> list[complex]:
        """
        Convert raw byte buffer to IQ samples.

        This method converts the raw byte buffer from the HackRF device into
        a list of complex IQ samples representing the in-phase (I) and
        quadrature (Q) components of the signal.

        Parameters
        ----------
        buffer : bytearray
            A bytearray containing the raw data bytes received from the HackRF device.

        Returns
        -------
        list of complex
            A list of complex numbers where each complex number represents an IQ sample.

        Notes
        -----
        The conversion process differs depending on whether the numpy library is available.
        With numpy, the method leverages efficient array operations to convert and normalize
        the IQ data. Without numpy, the method performs the conversion manually.

        The raw data bytes are interpreted as signed 8-bit integers and normalized to
        the range [-1, 1] for both the I and Q components.

        See Also
        --------
        read_samples : Method to read predefined number of samples into buffer and return them as numpy array.
        start_rx : Method to start receiving data, collecting it into a buffer.
        stop_rx : Method to stop receiving data.
        """
        if np:
            values = np.array(buffer).astype(np.int8)
            iq = values.astype(np.float64).view(np.complex128)
            iq /= 127.5
            iq -= 1 + 1j
        else:
            values = [
                int.from_bytes([x], byteorder="little", signed=True) for x in buffer
            ]
            iq = []
            for i in range(0, len(values), 2):
                real = values[i] / 127.5 - 1
                imag = values[i + 1] / 127.5 - 1
                iq.append(complex(real, imag))

        return iq

    @property
    def buffer_freqs(self) -> dict[int, deque]:
        """
        Get the current buffer frequencies.

        This property getter method retrieves the dictionary that holds frequency data buffers.
        Each key in the dictionary represents a frequency in Hz, and the corresponding value
        is a deque containing the collected data points for that frequency.

        Returns
        -------
        dict[int, deque]
            A dictionary where the keys are frequency values (in Hz) as integers, and the values
            are deques containing the collected data points for each frequency.

        Notes
        -----
        The frequency data buffer is useful for holding incoming data points collected during
        frequency sweeps or other operations. The buffer for each frequency is stored as a deque
        to efficiently append new data points and maintain a fixed size.
        """
        return self._buffer_freqs

    @buffer_freqs.setter
    def buffer_freqs(self, values: dict[int, deque]) -> None:
        """
        Set the frequency data buffer.

        This method allows setting a dictionary of frequency data buffers where each
        key represents a frequency and the corresponding value is a deque of data
        points collected at that frequency.

        Parameters
        ----------
        values : dict[int, deque]
            A dictionary where keys are frequency values (in Hz) as integers, and
            values are deques containing the collected data points for each frequency.

        Returns
        -------
        None

        Notes
        -----
        The frequency data buffer is useful for holding incoming data points
        collected during frequency sweeps or other operations. The buffer for each
        frequency is stored as a deque to efficiently append new data points and
        maintain a fixed size.
        """
        self._buffer_freqs = values

    def _sweep_callback(self, hackrf_transfer: lib_hackrf_transfer) -> int:
        """
        Callback function for handling data during a frequency sweep.

        This function processes incoming data blocks during a frequency sweep operation.
        It extracts the frequency and corresponding IQ data from the transferred data,
        and updates the internal buffer with the processed results. The callback
        also handles stopping conditions for the sweep.

        Parameters
        ----------
        hackrf_transfer : lib_hackrf_transfer
            A ctypes structure containing the buffer and transfer-related information
            from the HackRF device.

        Returns
        -------
        int
            Returns 1 if the sweep should stop (i.e., the transceiver mode is set to OFF),
            otherwise returns 0 to continue the sweep.

        Notes
        -----
        - This function will be provided to the HackRF library and called internally during
          a sweep operation.
        - The incoming data is segmented into blocks, with each block containing a header
          and IQ samples. The header includes frequency information which is extracted
          and associated with the corresponding IQ data.
        - The processed IQ data is stored in a deque, with a maximum length specified by
          `_buffer_size`.
        - If a `sweep_pipe_function` is defined, it is called with the updated buffer frequencies
          and sweep configuration. The function should return a boolean indicating whether the
          sweep should stop.
        """
        data = bytearray(
            cast(
                hackrf_transfer.contents.buffer,
                POINTER(c_byte * hackrf_transfer.contents.buffer_length),
            ).contents
        )

        BLOCKS_PER_TRANSFER = 16
        block_size = len(data) // BLOCKS_PER_TRANSFER

        for block_index in range(BLOCKS_PER_TRANSFER):

            offset = block_index * block_size

            header = data[offset : offset + 10]
            frequency = struct.unpack("<Q", header[2:])[0]

            block_data = self.get_iq(data[offset + 10 : offset + block_size])

            self._buffer_freqs.setdefault(
                frequency, deque(maxlen=self._buffer_size)
            ).extend(block_data)

        self._callback_counter += 1

        if self._callback_counter % self._blocks_per_callback == 0:
            if self._sweep_pipe_function is not None:
                stop = self._sweep_pipe_function(self._buffer_freqs, self._sweep_config)
                if stop:
                    self._transceiver_mode = TransceiverMode.HACKRF_TRANSCEIVER_MODE_OFF
                    self._bias_tee_on = False
                    return 1

        return 0

    def start_sweep(
        self,
        bands: list[tuple[int, int]],
        num_bytes: int = 16384,
        step_width: int = 1000000,
        pipe_function: Callable[[dict], dict] = None,
        step_offset: int = None,
        interleaved: bool = True,
        buffer_size: int = 16374,
        blocks_per_callback: int = 1,
    ) -> None:
        """
        Initiate a frequency sweep scan over multiple bands.

        This method configures the HackRF device to perform a frequency sweep scan across specified bands.
        The frequency ranges for the bands, the number of bytes to collect per step, and other parameters
        can be customized as needed.

        Parameters
        ----------
        bands : list of tuple[int, int]
            A list of tuples where each tuple specifies the start and end frequencies for a band in Hz.
            The number of bands is limited to MAX_SWEEP_RANGES as defined by libhackrf.
        num_bytes : int, optional
            Number of bytes to collect per tuning step, must be a multiple of 16384. Default is 16384.
        step_width : int, optional
            The width of each frequency step in Hz, default is 1000000 (1 MHz).
        pipe_function : callable, optional
            A function that handles data upon arrival. It takes a dictionary as an argument where keys are
            center frequencies and values are corresponding data bytes. The function should return a boolean
            indicating whether to stop the sweep. Default is None.
        step_offset : int, optional
            Offset to add to each tuning step. Default is the sampling rate divided by 2.
        interleaved : bool, optional
            If True, enable interleaved sweep style. Default is True.
        buffer_size : int, optional
            Size of the buffer for each band in bytes. Default is 16374.
        blocks_per_callback: int, optional
            Subsample rate for sweep callback; defines how often _sweep_pipe_function is called.

        Raises
        ------
        ValueError
            If the provided number of bands exceeds MAX_SWEEP_RANGES, or if num_bytes is not a multiple of 16384.

        RuntimeError
            If there is any error during the initialization or operation of the sweep scan.

        Notes
        -----
        - MAX_SWEEP_RANGES is a constant that limits the number of frequency bands that can be swept.
        - BYTES_PER_BLOCK is another constant defining the block size, which num_bytes must be a multiple of.
        - The sampling rate impacts the step_offset if it's not specified.
        - The pipe_function should handle arriving data and return True if the sweep should stop.

        See Also
        --------
        start_rx : Method to start receiving data.
        stop_rx : Method to stop receiving data.
        """
        MAX_SWEEP_RANGES = 10
        BYTES_PER_BLOCK = 16384

        self._callback_counter = 0

        if len(bands) > MAX_SWEEP_RANGES:
            raise ValueError(
                f"Number of sweep ranges must be less than or equal to MAX_SWEEP_RANGES ({MAX_SWEEP_RANGES}) "
            )
        if num_bytes % BYTES_PER_BLOCK:
            raise ValueError(
                f"Number of bytes per band must be a multiple of BYTES_PER_BLOCK ({BYTES_PER_BLOCK})"
            )
        band_freqs = []
        for band in bands:
            band_freqs.append(min(band[0], band[1]))
            band_freqs.append(max(band[0], band[1]))

        if step_offset is None:
            step_offset = self._sample_rate / 2

        self._check_error(
            libhackrf.hackrf_init_sweep(
                self._device_pointer,
                (c_uint16 * len(band_freqs))(*band_freqs),
                len(bands),
                int(num_bytes),
                int(step_width),
                int(step_offset),
                1 if interleaved else 0,
            )
        )

        self._sweep_pipe_function = pipe_function
        self._sample_count = 0
        self._blocks_per_callback = blocks_per_callback
        # self._freqs_count = len(band_freqs)
        self._buffer_freqs = {}
        self._buffer_size = buffer_size
        self._buffer_freqs = {}
        self._sweep_config = {
            "step_offset": step_offset,
            "sample_rate": self._sample_rate,
            "num_bytes": num_bytes,
            "step_width": step_width,
            "interleaved": interleaved,
            "buffer_size": buffer_size,
            "bands": bands,
        }

        self._transceiver_mode = TransceiverMode.TRANSCEIVER_MODE_RX_SWEEP
        self._check_error(
            libhackrf.hackrf_start_rx_sweep(
                self._device_pointer, self._cfunc_sweep_callback, None
            )
        )

    def _tx_callback(self, hackrf_transfer: lib_hackrf_transfer) -> int:
        """
        Feed data from buffer into the HackRF device in chunks.

        This callback function is responsible for transmitting data from the `buffer`
        attribute to the HackRF device in portions, as specified by the HackRF library
        documentation. It handles the segmentation of the buffer into smaller chunks
        and updates the hackrf_transfer structure accordingly.

        Parameters
        ----------
        hackrf_transfer : lib_hackrf_transfer
            A ctypes structure containing the buffer and other transfer-related
            information needed for the HackRF device.

        Returns
        -------
        int
            Returns 1 if no more data is needed, otherwise returns 0.

        Notes
        -----
        - This function will be used internally by the HackRF library's start_tx function.
        - The function will mark the transceiver mode as OFF and disable the bias tee
          once all data in the buffer has been transmitted.
        """
        CHUNK_SIZE = 1000000
        chunk, self.buffer = (
            self.buffer[0:CHUNK_SIZE],
            self.buffer[CHUNK_SIZE:],
        )
        hackrf_transfer.contents.buffer = (c_byte * len(chunk)).from_buffer(
            bytearray(chunk)
        )
        hackrf_transfer.contents.valid_length = len(chunk)
        if not len(self.buffer):
            self._transceiver_mode = TransceiverMode.HACKRF_TRANSCEIVER_MODE_OFF
            self._bias_tee_on = False
            return 1
        return 0

    def start_tx(self) -> None:
        """
        Start transmitting data from `self.buffer` to the HackRF device.

        This method initializes the transmission process, sending the data contained
        in the `buffer` attribute to the HackRF device. The transmission continues
        until the buffer is empty or explicitly stopped by the `stop_rx()` method.

        Notes
        -----
        - The buffer must contain the data to be transmitted before calling this method.
        - The transmission process can be halted by calling `stop_rx()`.

        Raises
        ------
        RuntimeError
            If there is an error starting the transmission on the device.

        See Also
        --------
        HackRF.stop_tx : Method to stop the ongoing transmission.
        """
        self._transceiver_mode = TransceiverMode.HACKRF_TRANSCEIVER_MODE_TRANSMIT
        self._check_error(
            libhackrf.hackrf_start_tx(
                self._device_pointer,
                self._cfunc_tx_callback,
                None,
            )
        )

    def stop_tx(self) -> None:
        """
        Stop transmitting data.

        This method stops the data transmission that was started by the `start_tx()` method.
        It can also be used to stop any ongoing transmission initiated by other methods
        under multithreading or multiprocessing conditions.

        Raises
        ------
        RuntimeError
            If there is an error stopping the transmission on the device.

        Notes
        -----
        This method sets the transceiver mode to `TransceiverMode.HACKRF_TRANSCEIVER_MODE_OFF`
        and disables the bias tee if it was enabled.
        """
        self._transceiver_mode = TransceiverMode.HACKRF_TRANSCEIVER_MODE_OFF
        self._bias_tee_on = False
        self._check_error(libhackrf.hackrf_stop_tx(self._device_pointer))

    @property
    def center_freq(self) -> int:
        """
        Get the current center frequency in Hertz.

        Returns
        -------
        int
            The current center frequency in Hertz.

        Notes
        -----
        The center frequency is a critical parameter that determines the frequency range
        the HackRF device is tuned to. This property retrieves the frequency currently
        set on the device.

        See Also
        --------
        HackRF.center_freq : Property to set the center frequency.
        HackRF.sample_rate : Property to get or set the sampling rate.
        """
        return self._center_freq

    @center_freq.setter
    def center_freq(self, freq: int) -> None:
        """
        Set center frequency in Hertz.

        Parameters
        ----------
        freq : int
            The desired center frequency to set, in Hertz.

        Raises
        ------
        RuntimeError
            If there is an error applying the center frequency to the HackRF device.

        Notes
        -----
        This setter method is responsible for adjusting the HackRF device's center frequency,
        affecting the signal's tuning. Ensure that the frequency value is within the valid
        range for your specific HackRF hardware configuration.

        See Also
        --------
        HackRF.sample_rate : Property to get or set the sampling rate.
        HackRF.filter_bandwidth : Property to get or set the baseband filter bandwidth.
        """
        freq = int(freq)
        self._check_error(libhackrf.hackrf_set_freq(self._device_pointer, freq))
        self._center_freq = freq

    @property
    def sample_rate(self) -> int:
        """
        Get the current sampling rate of the HackRF device.

        Returns
        -------
        int
            The current sampling rate in Hertz.

        Notes
        -----
        The sampling rate defines the number of samples per second captured or
        transmitted by the HackRF device.
        """
        return self._sample_rate

    @sample_rate.setter
    def sample_rate(self, rate: int) -> None:
        """
        Set the sampling rate in Hertz.

        Setting the sample rate will also automatically configure the baseband filter to 0.75 times the sampling rate,
        rounded down to the nearest valid value within `BASEBAND_FILTER_VALID_VALUES`.

        Parameters
        ----------
        rate : int
            The desired sampling rate in Hertz.

        Raises
        ------
        RuntimeError
            If there is an error applying the sampling rate to the HackRF device.

        Notes
        -----
        This method not only sets the sampling rate but also adjusts the baseband filter bandwidth accordingly.
        The baseband filter bandwidth is a critical parameter for defining the passband of the signal being received or transmitted.

        See Also
        --------
        HackRF.filter_bandwidth : Property to get or set the baseband filter bandwidth.
        BASEBAND_FILTER_VALID_VALUES : List of valid baseband filter bandwidths as specified by libhackrf.
        """
        self._check_error(libhackrf.hackrf_set_sample_rate(self._device_pointer, rate))
        self._filter_bandwidth = min(
            BASEBAND_FILTER_VALID_VALUES,
            key=lambda x: (abs(x - 0.75 * rate) if x - 0.75 * rate < 0 else 1e8),
        )
        self._sample_rate = rate
        return

    @property
    def filter_bandwidth(self) -> int:
        """
        Get the current baseband filter bandwidth in Hz.

        Returns
        -------
        int
            The baseband filter bandwidth in Hz.

        Notes
        -----
        The baseband filter bandwidth is automatically set based on the sample rate,
        specifically to 0.75 times the sample rate, rounded down to one of the valid values
        defined in `BASEBAND_FILTER_VALID_VALUES`.
        """
        return self._filter_bandwidth

    @filter_bandwidth.setter
    def filter_bandwidth(self, value_hz: int) -> None:
        """
        Set baseband filter bandwidth in Hz.

        This value will be changed if sampling rate changes (HackRF computes it automatically
        to be 0.75 x sampling rate, rounded down to one of the accepted values in BASEBAND_FILTER_VALID_VALUES).
        Therefore, this needs to be called after each sampling rate change given the new conditions.

        Parameters
        ----------
        value_hz : int
            The desired bandwidth value in Hz.

        Raises
        ------
        RuntimeError
            If there is an error applying the bandwidth setting to the HackRF device.

        Notes
        -----
        This setter method will round the requested value to the closest accepted one (not necessarily round down).

        See Also
        --------
        HackRF.sample_rate : Property to get or set the sampling rate, which affects the baseband filter bandwidth.
        BASEBAND_FILTER_VALID_VALUES : List of valid baseband filter bandwidths as specified by libhackrf.
        """
        value_hz = min(BASEBAND_FILTER_VALID_VALUES, key=lambda x: abs(x - value_hz))
        self._check_error(
            libhackrf.hackrf_set_baseband_filter_bandwidth(
                self._device_pointer, value_hz
            )
        )
        self._filter_bandwidth = value_hz

    @property
    def lna_gain(self) -> int:
        """
        Get current low noise amplifier (LNA) gain value.

        This property retrieves the current gain value set for the low noise amplifier
        in the HackRF device.

        Returns
        -------
        int
            The current LNA gain value, ranging from 0 to 40 dB in steps of 8. The value
            is rounded down to the nearest multiple of 8.

        Raises
        ------
        RuntimeError
            If there is an error retrieving the LNA gain from the device, a runtime exception
            will be raised.

        Notes
        -----
        LNA gain is crucial for improving the sensitivity of the HackRF device. Adjusting
        this value can help in scenarios where the incoming signal is weak and requires
        amplification.

        See Also
        --------
        HackRF.vga_gain : Property to get or set the Variable Gain Amplifier (VGA) gain value.
        HackRF.txvga_gain : Property to get or set the transmit amplifier gain value.
        """
        return self.lna_gain

    @lna_gain.setter
    def lna_gain(self, value: int) -> None:
        """
        Set low noise amplifier (LNA) gain.

        This method sets the gain value for the low noise amplifier in the HackRF device.
        The value is an integer ranging from 0 to 40 and is rounded down to the nearest multiple of 8.

        Parameters
        ----------
        value : int
            Desired LNA gain value. This should be between 0 and 40. Values are automatically rounded down to the nearest multiple of 8.

        Raises
        ------
        RuntimeError
            If there is an error setting the LNA gain on the device, a runtime exception will be raised.

        Notes
        -----
        The LNA gain is an essential parameter for improving the sensitivity of the device.
        Adjusting this can help in scenarios where the incoming signal is weak but needs amplification without introducing significant noise.
        """
        value = min(value, 40)
        value = max(value, 0)
        # rounds down to multiple of 8 (15 -> 8, 39 -> 32), etc.
        # internally, hackrf_set_lna_gain does the same thing
        # But we take care of it so we can keep track of the correct gain
        value -= value % 8
        self._check_error(libhackrf.hackrf_set_lna_gain(self._device_pointer, value))
        self._lna_gain = value

    @property
    def vga_gain(self) -> int:
        """
        Get the current Variable Gain Amplifier (VGA) gain value.

        The VGA gain is a configurable gain setting within the HackRF device
        that allows for adjusting the signal's amplification. This property getter
        method retrieves the current gain value that has been set for the VGA.

        Returns
        -------
        int
            The current VGA gain value in dB. This value ranges from 0 to 62.

        Raises
        ------
        RuntimeError
            If there is an error retrieving the VGA gain value from the device.

        Notes
        -----
        The VGA allows finer control over the signal's amplification compared to the
        Low Noise Amplifier (LNA). The appropriate gain setting can enhance signal
        clarity and strength, particularly in scenarios where the signal may suffer
        from interference or attenuation.

        See Also
        --------
        HackRF.lna_gain : Method to get or set the Low Noise Amplifier gain.
        HackRF.txvga_gain : Method to get or set the Transmit Variable Gain Amplifier gain.
        """
        return self._vga_gain

    @vga_gain.setter
    def vga_gain(self, value: int) -> None:
        """
        Set variable gain amplifier (VGA) gain value.

        Parameters
        ----------
        value : int
            The desired VGA gain value, ranging from 0 to 62 in steps of 2.
            Values exceeding the upper or lower limits will be clamped to the nearest valid value.

        Raises
        ------
        RuntimeError
            If there is an error setting the VGA gain on the device, a runtime
            exception will be raised with an appropriate error message.

        Notes
        -----
        The VGA gain value is internally rounded down to the nearest valid multiple of 2 before being
        set on the device. Internally, the HackRF `hackrf_set_vga_gain` function is used to set this value.

        See Also
        --------
        HackRF.lna_gain : Method to set the Low Noise Amplifier gain.
        """
        value = min(value, 62)
        value = max(value, 0)
        value -= value % 2
        self._check_error(libhackrf.hackrf_set_vga_gain(self._device_pointer, value))
        self._vga_gain = value

    @property
    def amplifier_on(self) -> bool:
        """
        Check if the 14 dB frontend RF amplifier is enabled or disabled.

        This property getter method checks the state of the 14 dB frontend RF amplifier.
        The amplifier enhances the signal strength by providing an additional 14 dB of gain.

        Returns
        -------
        bool
            True if the 14 dB frontend RF amplifier is enabled, False if it is disabled.

        Notes
        -----
        The frontend RF amplifier is useful for improving the signal strength, particularly in scenarios with weak signals.
        The state of the amplifier is managed internally and will be reset when the device goes to idle.
        """
        return self._amplifier_on

    @amplifier_on.setter
    def amplifier_on(self, enable: bool) -> None:
        """
        Enable or disable the 14 dB frontend RF amplifier.

        Parameters
        ----------
        enable : bool
            If True, the 14 dB frontend RF amplifier will be enabled.
            If False, the amplifier will be disabled.

        Raises
        ------
        RuntimeError
            If there is an error enabling or disabling the amplifier,
            a runtime exception will be raised.

        Notes
        -----
        The amplifier is useful for improving the signal strength by providing
        an additional 14 dB of gain. This can be beneficial in scenarios with
        weak signals. The amplifier state will be reset when the device goes
        to idle.
        """
        self._check_error(
            libhackrf.hackrf_set_amp_enable(self._device_pointer, 1 if enable else 0)
        )

    @property
    def bias_tee_on(self) -> bool:
        """
        Check if bias voltage of 3.3 V (50 mA max!) is applied to the antenna.

        This property getter method checks whether the 3.3 V bias voltage is currently
        applied to the antenna. The bias voltage is useful for powering active antennas
        or other external components that require a bias voltage when connected to the
        HackRF device.

        Returns
        -------
        bool
            True if the 3.3 V bias voltage is enabled, False if it is disabled.
        """
        return self._bias_tee_on

    @bias_tee_on.setter
    def bias_tee_on(self, enable: bool) -> None:
        """
        Enable and disable 3.3V bias voltage on antenna (50 mA max!).

        This method allows you to enable or disable the 3.3V bias voltage applied on the antenna.
        The bias voltage is limited to a maximum of 50 mA. This bias voltage will be disabled
        automatically when the device goes to idle.

        Parameters
        ----------
        enable : bool
            If True, the 3.3V bias voltage will be enabled. If False, the bias voltage will be disabled.

        Raises
        ------
        RuntimeError
            If there is an error enabling or disabling the bias voltage, a runtime exception will be raised.

        Notes
        -----
        The bias voltage is useful for powering active antennas or other external components
        that require a bias voltage when connected to the HackRF.
        """
        self._check_error(
            libhackrf.hackrf_set_antenna_enable(
                self._device_pointer, 1 if enable else 0
            )
        )
        self._bias_tee_on = enable

    @property
    def txvga_gain(self) -> int:
        """
        Get transmit amplifier gain.

        This property getter method retrieves the current transmit amplifier gain
        for the HackRF device. The gain value is an integer representing the
        transmit amplifier gain in dB.

        Returns
        -------
        int
            The current transmit amplifier gain in dB. This value ranges from 0 to 47.
        """
        return self._txvga_gain

    @txvga_gain.setter
    def txvga_gain(self, value: int) -> None:
        """
        Set transmit amplifier gain.

        This property setter method sets the transmit amplifier gain for the HackRF device.
        The gain value should be in the range from 0 to 47 dB.

        Parameters
        ----------
        value : int
            The desired transmit amplifier gain in dB. This value will be constrained to
            the range [0, 47] if out-of-bounds values are provided.

        Raises
        ------
        RuntimeError
            If there is an error setting the transmit amplifier gain on the device, a runtime
            exception will be raised.

        Notes
        -----
        The gain value will be set to the HackRF using the `hackrf_set_txvga_gain` function
        from the `libhackrf` C library.

        The value passed to the device will be clamped within the valid range, ensuring it
        remains between 0 and 47 dB.
        """
        value = min(value, 47)
        value = max(value, 0)
        self._check_error(libhackrf.hackrf_set_txvga_gain(self._device_pointer, value))
        self._txvga_gain = value

    @property
    def sample_count_limit(self) -> int:
        """
        Get the current receive buffer limit.

        The `sample_count_limit` property retrieves the maximum number of
        bytes that will be collected during data acquisition. If the limit
        is set to 0, the `start_rx()` method will continue to collect data
        until `stop_rx()` is called.

        Returns
        -------
        int
            The maximum number of bytes to be collected. A value of 0 indicates
            unlimited collection until manually stopped.
        """
        return self._sample_count_limit

    @sample_count_limit.setter
    def sample_count_limit(self, bytes: int) -> None:
        """
        Set receive buffer limit.

        The `sample_count_limit` method defines the maximum number of bytes to be collected during data acquisition.
        When the limit is set to a non-zero value, the `start_rx()` method will stop data collection upon reaching this limit.
        If the limit is set to 0, data collection will continue until explicitly stopped by the `stop_rx()` method.

        Parameters
        ----------
        bytes : int
            The maximum number of bytes to be collected. A value of 0 indicates unlimited collection until stopped manually.
        """
        self._sample_count_limit = bytes

    def get_serial_no(self) -> str:
        """
        Retrieve the serial number of the connected HackRF device.

        This function reads the serial number from the HackRF device and
        returns it as a hexadecimal string.

        Returns
        -------
        str
            The serial number of the HackRF device in hexadecimal format.

        Raises
        ------
        RuntimeError
            If there is an error in retrieving the serial number from the device.
        """
        sn = lib_read_partid_serialno_t()
        self._check_error(
            libhackrf.hackrf_board_partid_serialno_read(self._device_pointer, sn)
        )
        return "".join([f"{sn.serial_no[i]:08x}" for i in range(4)])
