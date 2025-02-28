import numpy as np
import scipy


# Zero out samples that fall below the amplitude threshold.
def simple_squelch(iq_samples: np.ndarray, threshold: float = 0.01) -> np.ndarray:
    return np.where(np.abs(iq_samples) < threshold, 0, iq_samples)


# Applies a decimating FIR low-pass filter.
def decimating_fir_filter(
    data: np.ndarray, decimation: int, gain: float, fs: int, cutoff_freq, transition_width, window="hamming"
) -> np.ndarray:
    nyquist = fs / 2
    num_taps = int(4 * nyquist / transition_width)  # Rule of thumb for FIR filter length
    num_taps |= 1  # Ensure odd number of taps

    # Design FIR filter
    taps = scipy.signal.firwin(num_taps, cutoff=cutoff_freq / nyquist, window=window, pass_zero=True)
    taps *= gain  # Apply gain

    # Filter and decimate
    filtered = scipy.signal.lfilter(taps, 1.0, data)
    decimated = filtered[::decimation]  # Downsample
    return decimated


# Apply FIR filtering (convolution) with the given taps
def fir_filter(data: np.ndarray, taps) -> np.ndarray:
    return np.convolve(data, taps, mode="same")


# Additive White Gaussian Noise
def add_awgn(signal, snr_db):
    signal_power = np.mean(np.abs(signal) ** 2)
    snr_linear = 10 ** (snr_db / 10)  # Calculate the noise power based on the SNR (in dB)
    noise_power = signal_power / snr_linear
    noise = np.sqrt(noise_power) * np.random.randn(len(signal))
    return signal + noise
