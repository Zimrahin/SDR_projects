import numpy as np
import scipy

from modulation import modulate_frequency, pulse_shape_bits_fir, gaussian_fir_taps, oqpsk_modulate, half_sine_fir_taps
from packet_utils import (
    create_ble_phy_packet,
    unpack_uint8_to_bits,
    create_802154_phy_packet,
    map_nibbles_to_chips,
    split_iq_chips,
)


class TransmitterBLE:
    # Class variables
    transmission_rate: float = 1e6  # BLE 1 Mb/s
    fsk_deviation_ble: float = 250e3  # Hz
    bt: float = 0.5  # Bandwidth-bit period product for Gaussian pulse shaping

    def __init__(self, fs: int | float):
        # Instance variables
        self.fs = fs  # Sampling rate
        # For now, assume sampling rate is an integer multiple of transmission rate.
        # For generalisation, it's necessary to implement a rational resampler to generate the final IQ signal.
        self.sps: int = int(self.fs / self.transmission_rate)  # Samples per symbol

    # Receives a binary array and returns IQ GFSK modulated compplex signal.
    def modulate(self, bits: np.ndarray, zero_padding: int = 0) -> np.ndarray:
        """Receives a binary array and returns IQ GFSK modulated complex signal."""

        # Generate Gaussian taps and convolve with rectangular window
        gauss_taps = gaussian_fir_taps(sps=self.sps, ntaps=self.sps, bt=self.bt)
        gauss_taps = scipy.signal.convolve(gauss_taps, np.ones(self.sps))

        # Apply Gaussian pulse shaping with BT = 0.5 (BLE PHY specification)
        pulse_shaped_symbols = pulse_shape_bits_fir(bits, fir_taps=gauss_taps, sps=self.sps)

        # Frequency modulation
        iq_signal = modulate_frequency(pulse_shaped_symbols, self.fsk_deviation_ble, self.fs)

        # Append zeros
        iq_signal = np.concatenate(
            (np.zeros(zero_padding, dtype=iq_signal.dtype), iq_signal, np.zeros(zero_padding, dtype=iq_signal.dtype))
        )

        return iq_signal

    # Receive payload (bytes) and base address to create physical BLE packet (bits)
    def process_phy_payload(self, payload: np.ndarray, base_address: int = 0x12345678) -> np.ndarray:
        """Receive payload (bytes) and base address to create physical BLE packet."""

        # Append header, CRC and apply whitening
        byte_packet = create_ble_phy_packet(payload, base_address)

        # Unpack bytes into bits, LSB first as sent on air
        bits_packet = unpack_uint8_to_bits(byte_packet)

        return bits_packet


class Transmitter802154:
    # Class variables
    transmission_rate: float = 2e6  # 2 Mchip/s
    max_payload_size: int = 127

    # Chip mapping for IEEE 802.15.4 O-QPSK DSSS encoding
    chip_mapping: np.ndarray = np.array(
        [
            0xD9C3522E,  # 0
            0xED9C3522,  # 1
            0x2ED9C352,  # 2
            0x22ED9C35,  # 3
            0x522ED9C3,  # 4
            0x3522ED9C,  # 5
            0xC3522ED9,  # 6
            0x9C3522ED,  # 7
            0x8C96077B,  # 8
            0xB8C96077,  # 9
            0x7B8C9607,  # A
            0x77B8C960,  # B
            0x077B8C96,  # C
            0x6077B8C9,  # D
            0x96077B8C,  # E
            0xC96077B8,  # F
        ],
        dtype=np.uint32,
    )

    def __init__(self, fs: int | float):
        # Instance variables
        self.fs = fs  # Sampling rate
        # For now, assume sampling rate is an integer multiple of transmission rate.
        # For generalisation, it's necessary to implement a rational resampler to generate the final IQ signal.
        self.sps: int = int(2 * self.fs / self.transmission_rate)  # Samples per chip

    # Receives a chip uint32 array and returns IQ O-QPSK modulated complex signal.
    def modulate(self, chips: np.ndarray, zero_padding: int = 0) -> np.ndarray:
        """Receives a chip uint32 array and returns IQ O-QPSK modulated complex signal."""

        I_chips, Q_chips = split_iq_chips(chips)  # Maps a the even and odd chips to I chips and Q chips respectively.
        half_sine_pulse = half_sine_fir_taps(self.sps)  # Generate the half-sine pulse
        iq_signal = oqpsk_modulate(I_chips, Q_chips, half_sine_pulse, self.sps)  # O-QPSK modulation

        # Append zeros
        iq_signal = np.concatenate(
            (np.zeros(zero_padding, dtype=iq_signal.dtype), iq_signal, np.zeros(zero_padding, dtype=iq_signal.dtype))
        )

        return iq_signal

    # Creates physical packet and maps it to an array of uint32 chips. CRC is optional.
    def process_phy_payload(self, payload: np.ndarray, append_crc: bool = True) -> np.ndarray:
        """Creates physical packet and maps it to an array of uint32 chips. CRC is optional."""

        # Append header and optional CRC
        byte_packet = create_802154_phy_packet(payload, append_crc=append_crc)

        # Maps bytes to array of uint32 chips
        chips = map_nibbles_to_chips(byte_packet, self.chip_mapping, return_string=False)

        return chips
