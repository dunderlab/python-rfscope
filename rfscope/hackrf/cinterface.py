"""""" """
cinterface.py module for interfacing with the HackRF software-defined radio (SDR) hardware.

This module contains definitions and functions for managing communication with HackRF devices
using ctypes to interface with the underlying C library. It includes functionality for
initialization, opening devices, setting parameters, and handling data transfers.

Key Functionalities
--------------------
- Initialize and configure HackRF devices.
- Open and close device communications.
- Manage data transmission and reception.
- Handle errors and exceptions.

"""

from ctypes import *
from enum import Enum

LIBNAME = "libhackrf.so.0"
libhackrf = CDLL(LIBNAME)


ERRORS = {
    0: "OK",
    1: "True",
    -2: "Invalid parameter (HACKRF_ERROR_INVALID_PARAM)",
    -5: "USB device not found (HACKRF_ERROR_NOT_FOUND)",
    -6: "Devicy busy (HACKRF_ERROR_BUSY)",
    -11: "Memory allocation failed in libhackrf (HACKRF_ERROR_NO_MEM)",
    -1000: "libusb error  (HACKRF_ERROR_LIBUSB)",
    -1001: "Error setting up transfer thread (HACKRF_ERROR_THREAD)",
    -1002: "Streaming thread could not start due to an error (HACKRF_ERROR_STREAMING_THREAD_ERR)",
    -1003: "Streaming thread stopped due to an error (HACKRF_ERROR_STREAMING_STOPPED)",
    -1004: "Streaming thread exited normally (HACKRF_ERROR_STREAMING_EXIT_CALLED)",
    -1005: "The installed firmware does not support this function (HACKRF_ERROR_USB_API_VERSION)",
    -2000: "Can not exit library as one or more HackRFs still in use (HACKRF_ERROR_NOT_LAST_DEVICE)",
    -9999: "Unspecified error (HACKRF_ERROR_OTHER)",
}


class TransceiverMode(Enum):
    """Enumeration for the transceiver modes of the HackRF device.

    This enumeration represents the various operational modes of the HackRF transceiver.
    Each mode affects how the device interacts with signals and data processing.

    Attributes
    ----------
    HACKRF_TRANSCEIVER_MODE_OFF : int
        Transceiver mode that indicates no active operation. The device is in an idle state.
    HACKRF_TRANSCEIVER_MODE_RECEIVE : int
        Transceiver mode for receiving signals. In this mode, the device captures incoming data.
    HACKRF_TRANSCEIVER_MODE_TRANSMIT : int
        Transceiver mode for transmitting signals. The device sends data out during this operation.
    TRANSCEIVER_MODE_RX_SWEEP : int
        Transceiver mode for performing a frequency sweep. The device scans through a range of frequencies.

    Notes
    -----
    Refer to the HackRF device documentation for more details on signal handling and mode-specific operations.
    """

    HACKRF_TRANSCEIVER_MODE_OFF = 0
    HACKRF_TRANSCEIVER_MODE_RECEIVE = 1
    HACKRF_TRANSCEIVER_MODE_TRANSMIT = 2
    TRANSCEIVER_MODE_RX_SWEEP = 5


# Allowed values for baseband filter in MHz
BASEBAND_FILTER_VALID_VALUES = [
    1750000,
    2500000,
    3500000,
    5000000,
    5500000,
    6000000,
    7000000,
    8000000,
    9000000,
    10000000,
    12000000,
    14000000,
    15000000,
    20000000,
    24000000,
    28000000,
]

p_hackrf_device = c_void_p


# Data structures from libhackrf are named in accordance with C code and prefixed with lib_


class lib_hackrf_transfer(Structure):
    """Data structure for handling HackRF data transfer.

    This structure is utilized for managing the data transfer between the HackRF device
    and the host application. It encapsulates both the prepared data buffer and the
    necessary metadata for successful communication.

    Attributes
    ----------
    device : p_hackrf_device
        A pointer to the HackRF device instance.
    buffer : POINTER(c_byte)
        A pointer to the buffer that stores incoming or outgoing data.
    buffer_length : int
        The length of the data buffer in bytes.
    valid_length : int
        The length of valid data received or to be sent.
    rx_ctx : c_void_p
        Context pointer for receive operations, allowing custom data handling.
    tx_ctx : c_void_p
        Context pointer for transmit operations, allowing custom data handling.
    """

    _fields_ = [
        ("device", p_hackrf_device),
        ("buffer", POINTER(c_byte)),
        ("buffer_length", c_int),
        ("valid_length", c_int),
        ("rx_ctx", c_void_p),
        ("tx_ctx", c_void_p),
    ]


class lib_read_partid_serialno_t(Structure):
    """Data structure for reading the part ID and serial number of the HackRF device.

    This structure contains the part ID and serial number read from the HackRF
    hardware, enabling identification and management of the device.

    Attributes
    ----------
    part_id : c_uint32 * 2
        An array containing the part ID of the HackRF device. This can be used
        for verification and compatibility checks.
    serial_no : c_uint32 * 4
        An array containing the serial number of the HackRF device. This unique
        identifier helps in distinguishing between multiple connected devices.

    Notes
    -----
    Ensure to handle the values correctly, as the part ID and serial number are
    critical for device management.
    """

    _fields_ = [("part_id", c_uint32 * 2), ("serial_no", c_uint32 * 4)]


class lib_hackrf_device_list_t(Structure):
    """Data structure representing a list of HackRF devices.

    This structure holds information about the connected HackRF devices, including
    their serial numbers, USB board IDs, and the total count of devices detected.

    Attributes
    ----------
    serial_numbers : POINTER(c_char_p)
        A pointer to a list of serial numbers corresponding to connected HackRF devices.
    usb_board_ids : c_void_p
        A pointer to USB board IDs for the devices. The specific structure of this data is
        implementation-defined and relates to the USB protocol.
    usb_device_index : POINTER(c_int)
        A pointer to an array containing the USB device indexes for the connected HackRF devices.
    devicecount : c_int
        The total number of HackRF devices detected and listed in this structure.
    usb_devices : POINTER(c_void_p)
        A pointer to the USB device information for each connected HackRF. The exact
        structure is determined by the underlying library implementation.
    usb_devicecount : c_int
        The total number of USB devices recognized as HackRF devices.

    Notes
    -----
    This structure is used when interacting with the HackRF library to enumerate devices,
    open device connections, and manage multiple HackRF devices concurrently.

    """

    _fields_ = [
        ("serial_numbers", POINTER(c_char_p)),
        ("usb_board_ids", c_void_p),
        ("usb_device_index", POINTER(c_int)),
        ("devicecount", c_int),
        ("usb_devices", POINTER(c_void_p)),
        ("usb_devicecount", c_int),
    ]


libhackrf.hackrf_init.restype = c_int
libhackrf.hackrf_init.argtypes = []
libhackrf.hackrf_open.restype = c_int
libhackrf.hackrf_open.argtypes = [POINTER(p_hackrf_device)]
libhackrf.hackrf_device_list_open.restype = c_int
libhackrf.hackrf_device_list_open.arg_types = [
    POINTER(lib_hackrf_device_list_t),
    c_int,
    POINTER(p_hackrf_device),
]
libhackrf.hackrf_close.restype = c_int
libhackrf.hackrf_close.argtypes = [p_hackrf_device]

libhackrf.hackrf_set_sample_rate.restype = c_int
libhackrf.hackrf_set_sample_rate.argtypes = [p_hackrf_device, c_double]

libhackrf.hackrf_set_amp_enable.restype = c_int
libhackrf.hackrf_set_amp_enable.argtypes = [p_hackrf_device, c_uint8]

libhackrf.hackrf_set_lna_gain.restype = c_int
libhackrf.hackrf_set_lna_gain.argtypes = [p_hackrf_device, c_uint32]

libhackrf.hackrf_set_vga_gain.restype = c_int
libhackrf.hackrf_set_vga_gain.argtypes = [p_hackrf_device, c_uint32]

libhackrf.hackrf_start_rx.restype = c_int
libhackrf.hackrf_start_rx.argtypes = [
    p_hackrf_device,
    CFUNCTYPE(c_int, POINTER(lib_hackrf_transfer)),
    c_void_p,
]

libhackrf.hackrf_stop_rx.restype = c_int
libhackrf.hackrf_stop_rx.argtypes = [p_hackrf_device]

libhackrf.hackrf_device_list.restype = POINTER(lib_hackrf_device_list_t)

libhackrf.hackrf_set_freq.restype = c_int
libhackrf.hackrf_set_freq.argtypes = [p_hackrf_device, c_uint64]


libhackrf.hackrf_set_baseband_filter_bandwidth.restype = c_int
libhackrf.hackrf_set_baseband_filter_bandwidth.argtypes = [
    p_hackrf_device,
    c_uint32,
]


libhackrf.hackrf_board_partid_serialno_read.restype = c_int
libhackrf.hackrf_board_partid_serialno_read.argtypes = [
    p_hackrf_device,
    POINTER(lib_read_partid_serialno_t),
]

libhackrf.hackrf_init_sweep.restype = c_int
libhackrf.hackrf_init_sweep.argtypes = [
    p_hackrf_device,
    POINTER(c_uint16),
    c_uint,
    c_uint32,
    c_uint32,
    c_uint32,
    c_uint,
]

libhackrf.hackrf_start_rx_sweep.restype = c_int
libhackrf.hackrf_start_rx_sweep.argtypes = [
    p_hackrf_device,
    CFUNCTYPE(c_int, POINTER(lib_hackrf_transfer)),
    c_void_p,
]

libhackrf.hackrf_set_txvga_gain.restype = c_int
libhackrf.hackrf_set_txvga_gain.argtypes = [p_hackrf_device, c_uint32]

libhackrf.hackrf_set_antenna_enable.restype = c_int
libhackrf.hackrf_set_antenna_enable.argtypes = [p_hackrf_device, c_uint8]

libhackrf.hackrf_start_tx.restype = c_int
libhackrf.hackrf_start_tx.argtypes = [
    p_hackrf_device,
    CFUNCTYPE(c_int, POINTER(lib_hackrf_transfer)),
    c_void_p,
]

libhackrf.hackrf_stop_tx.restype = c_int
libhackrf.hackrf_stop_tx.argtypes = [p_hackrf_device]

if libhackrf.hackrf_init() != 0:
    raise RuntimeError(f"Unable to initialize libhackrf {LIBNAME}.")
