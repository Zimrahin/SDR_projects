import numpy as np


# Find a sequence of bits in a given binary dara array
def correlate_access_code(data: np.ndarray, access_code: str, threshold: int, reduce_mask: bool = False) -> np.ndarray:
    """Find a sequence of bits in a given binary dara array."""
    # access_code: from LSB to MSB (as samples arrive on-air)
    access_code = access_code.replace("_", "")
    code_len = len(access_code)
    access_int = int(access_code, 2)  # Convert the access code (e.g. "10110010") to an integer
    mask = (1 << code_len) - 1  # Create a mask to keep only the last code_len bits.
    if reduce_mask:
        # Create a mask that has ones everywhere except at the MSB and LSB:
        # This is useful for differential encoding in chip sequences for IEEE 802.15.4 demodulation
        reduced_mask = mask & ~((1 << (code_len - 1)) | 1)
    else:
        reduced_mask = mask
    data_reg = 0
    positions = []  # Positions where the access code has been found in data

    for i, bit in enumerate(data):
        bit = int(bit)
        data_reg = ((data_reg << 1) | (bit & 0x1)) & mask  # Shift in the new bit
        if i + 1 < code_len:  # Start comparing once data_reg is filled
            continue

        # Count the number of mismatched bits between data_reg and the access code
        mismatches = bin((data_reg ^ access_int) & reduced_mask).count("1")
        if mismatches <= threshold:
            # Report the position immediately after the access code was found
            positions.append(i + 1)

    return np.array(positions)


# Apply whintening (de-whitening) to an array of bytes
def ble_whitening(data: np.ndarray, lfsr=0x01, polynomial=0x11):
    """Apply whintening (de-whitening) to an array of bytes."""
    # LFSR default value is 0x01 as it is the default value in the nRF DATAWHITEIV register
    # The polynomial default value is 0x11 = 0b001_0001 -> x⁷ + x⁴ + 1 (x⁷ is omitted)
    output = np.empty_like(data)  # Initialise output array

    for idx, byte in enumerate(data):
        whitened_byte = 0
        for bit_pos in range(8):
            # XOR the current data bit with LFSR MSB
            lfsr_msb = (lfsr & 0x40) >> 6  # LFSR is 7-bit, so MSB is at position 6
            data_bit = (byte >> bit_pos) & 1  # Extract current bit
            whitened_bit = data_bit ^ lfsr_msb  # XOR

            # Update the whitened byte
            whitened_byte |= whitened_bit << (bit_pos)

            # Update LFSR
            if lfsr_msb:  # If MSB is 1 (before shifting), apply feedback
                lfsr = (lfsr << 1) ^ polynomial  # XOR with predefined polynomial
            else:
                lfsr <<= 1
            lfsr &= 0x7F  # 0x7F mask to keep ksfr within 7 bits

        output[idx] = whitened_byte

    return output, lfsr


# Pack a sequence of bits (array) into an array of bytes (integers)
def pack_bits_to_uint8(bits: np.ndarray) -> np.ndarray:
    """Pack a sequence of bits (array) into an array of bytes (integers)."""
    # Pack binary array LSB first ([1,1,1,1,0,0,0,0]) into bytes array ([0x0F])
    # Ensure the binary array length is a multiple of 8
    if len(bits) % 8 != 0:
        raise ValueError(f"The binary list {len(bits)} length must be a multiple of 8.")

    # Convert binary to NumPy array
    bits = np.array(bits, dtype=np.uint8)
    bits = bits.reshape(-1, 8)[:, ::-1]  #  LSB to MSB correction
    uint8_array = np.packbits(bits, axis=1).flatten()

    return uint8_array


# Computes the Cyclic Redundancy Check for a given array of bytes
def compute_crc(data: np.ndarray, crc_init: int = 0x00FFFF, crc_poly: int = 0x00065B, crc_size: int = 3) -> np.ndarray:
    """Computes the Cyclic Redundancy Check for a given array of bytes."""
    crc_mask = (1 << (crc_size * 8)) - 1  # Mask to n-byte width (0xFFFF for crc_size = 2)

    def swap_nbit(num, n):
        num = num & crc_mask
        reversed_bits = f"{{:0{n * 8}b}}".format(num)[::-1]
        return int(reversed_bits, 2)

    crc_init = swap_nbit(crc_init, crc_size)  # LSB -> MSB
    crc_poly = swap_nbit(crc_poly, crc_size)

    crc = crc_init
    for byte in data:
        crc ^= int(byte)
        for _ in range(8):  # Process each bit
            if crc & 0x01:  # Check the LSB
                crc = (crc >> 1) ^ crc_poly
            else:
                crc >>= 1
            crc &= crc_mask  # Ensure CRC size

    return np.array([(crc >> (8 * i)) & 0xFF for i in range(crc_size)], dtype=np.uint8)


# Generates (preamble + base address sequence) to use as access code
def generate_access_code_ble(base_address: int) -> str:
    """Generates (preamble + base address sequence) to use as access code."""
    base_address &= 0xFFFFFFFF  # 4-byte unsigned long
    preamble = 0x55 if base_address & 0x01 else 0xAA
    preamble = format(preamble, "08b")[::-1]

    base_address = base_address.to_bytes(4, byteorder="little")
    base_address = [format(byte, "08b")[::-1] for byte in base_address]
    address_prefix = "00000000"

    return "_".join([preamble] + base_address + [address_prefix])


# Returns a string of chips to be used by correlate access code function
def map_nibbles_to_chips(byte_array: list[int], chip_mapping: np.ndarray) -> str:
    """Returns a string of chips to be used by correlate access code function."""
    result = []
    for byte in byte_array:
        for nibble in [byte & 0x0F, (byte >> 4) & 0x0F]:  # Extract LSB first, then MSB
            mapped_value = chip_mapping[nibble]
            binary_string = f"{mapped_value:032b}"  # Convert to 32-bit binary
            result.append(binary_string)  # Append delimiter
    return "_".join(result)


# Return the number of set bits in the lowest 'bits' of 'n'.
def count_set_bits(n: int, bits: int = 32) -> int:
    """Return the number of set bits in the lowest 'bits' of 'n'."""
    mask = (1 << bits) - 1  # Create a mask for the lowest 'bits' bits
    return bin(n & mask).count("1")


# Decodes the received chip sequence by comparing it against a known mapping.
def decode_chips(chips32: int, chip_mapping: np.ndarray, threshold: int = 32) -> int:
    """Decodes the received chip sequence by comparing it against a known mapping."""
    best_match = 0xFF
    min_threshold = 33  # Value greater than the maximum possible errors (32 bits)

    for i in range(16):
        # 0x7FFFFFFE masks out the first and last bit, since these depend on previous chip data
        # This is because we are using differential encoding
        masked_diff = (chips32 ^ chip_mapping[i]) & 0x7FFFFFFE
        diff_bits = count_set_bits(masked_diff, 32)  # Count the number of bits that differ

        if diff_bits < min_threshold:
            best_match = i
            min_threshold = diff_bits

    if min_threshold <= threshold:
        return best_match & 0xF  # Return position in chip mapping

    return 0xFF  # If no valid match was found, return 0xFF to indicate an error.


# Pack chips into bytes. Assumes each byte is formed from 64 chips (32 per nibble).
def pack_chips_to_bytes(chips: np.ndarray, num_bytes: int, chip_mapping: np.ndarray, threshold: int) -> np.ndarray:
    """Pack chips into bytes. Assumes each byte is formed from 64 chips (32 per nibble)."""
    bytes_out = np.empty(num_bytes, dtype=np.uint8)

    for i in range(num_bytes):
        # Convert 32 chips into an integer
        nibble1 = chips_to_int(chips[i * 64 : i * 64 + 32])
        nibble2 = chips_to_int(chips[i * 64 + 32 : (i + 1) * 64])

        # Decode the nibbles
        nibble1 = decode_chips(nibble1, chip_mapping=chip_mapping, threshold=threshold)
        nibble2 = decode_chips(nibble2, chip_mapping=chip_mapping, threshold=threshold)

        # Pack into a byte
        bytes_out[i] = nibble1 | (nibble2 << 4)

    return bytes_out


# Convert a 32-length binary array to an integer.
def chips_to_int(chips: np.ndarray) -> int:
    """Convert a 32-length binary array to an integer."""
    assert len(chips) == 32, "Input must be exactly 32 elements long"
    return int("".join(map(str, chips)), 2)
