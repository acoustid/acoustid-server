from cpython cimport array
from cpython.bytes cimport PyBytes_AsString, PyBytes_FromStringAndSize
from libc.stdint cimport uint8_t, uint32_t

import array

# Binary fingerprint format v1:
#
# +--------+--------+--------+--------+
# | magic  | format | ver    | diffs  |
# +--------+--------+--------+--------+
# | 2B     | 1B     | 1B     | 4B[]   |
# +--------+--------+--------+--------+
#
# magic: 2-byte magic number ("Fp")
# format: 1-byte format version number
# ver: 1-byte fingerprint algorithm version
# diffs: array of 4-byte XOR differences between consecutive hash values (little-endian)
#
# After encoding to the binary format, the data is compressed using zstd.



cdef uint8_t MAGIC_B0 = ord('F')
cdef uint8_t MAGIC_B1 = ord('p')

cdef uint8_t FORMAT_VERSION = 1


cdef encode_fingerprint_list(list hashes, int version, bint signed):
    cdef uint32_t hash, last_hash, diff
    cdef int i, num_hashes = len(hashes)
    cdef bint from_signed = signed

    out = PyBytes_FromStringAndSize(NULL, 4 + num_hashes * 4)
    cdef uint8_t* buf = <uint8_t *>PyBytes_AsString(out)

    buf[0] = MAGIC_B0
    buf[1] = MAGIC_B1
    buf[2] = FORMAT_VERSION
    buf[3] = version

    if from_signed:
        last_hash = 0
        i = 0
        while i < num_hashes:
            hash = <uint32_t>(<int>hashes[i])
            diff = hash ^ last_hash
            last_hash = hash
            buf[4 + i * 4 + 0] = diff & 0xFF
            buf[4 + i * 4 + 1] = (diff >> 8) & 0xFF
            buf[4 + i * 4 + 2] = (diff >> 16) & 0xFF
            buf[4 + i * 4 + 3] = (diff >> 24) & 0xFF
            i += 1
    else:
        last_hash = 0
        i = 0
        while i < num_hashes:
            hash = hashes[i]
            diff = hash ^ last_hash
            last_hash = hash
            buf[4 + i * 4 + 0] = diff & 0xFF
            buf[4 + i * 4 + 1] = (diff >> 8) & 0xFF
            buf[4 + i * 4 + 2] = (diff >> 16) & 0xFF
            buf[4 + i * 4 + 3] = (diff >> 24) & 0xFF
            i += 1

    return out


cdef encode_fingerprint_array(array.array hashes, int version, bint signed):
    cdef uint32_t hash, last_hash, diff
    cdef int i, num_hashes = len(hashes)
    cdef bint from_signed = signed

    if hashes.itemsize != 4:
        raise TypeError("Invalid hashes array, need 32-bit items")

    out = PyBytes_FromStringAndSize(NULL, 4 + num_hashes * 4)
    cdef uint8_t* buf = <uint8_t *>PyBytes_AsString(out)

    buf[0] = MAGIC_B0
    buf[1] = MAGIC_B1
    buf[2] = FORMAT_VERSION
    buf[3] = version

    if from_signed:
        last_hash = 0
        i = 0
        while i < num_hashes:
            hash = hashes.data.as_ints[i]
            diff = hash ^ last_hash
            last_hash = hash
            buf[4 + i * 4 + 0] = diff & 0xFF
            buf[4 + i * 4 + 1] = (diff >> 8) & 0xFF
            buf[4 + i * 4 + 2] = (diff >> 16) & 0xFF
            buf[4 + i * 4 + 3] = (diff >> 24) & 0xFF
            i += 1
    else:
        last_hash = 0
        i = 0
        while i < num_hashes:
            hash = hashes.data.as_uints[i]
            diff = hash ^ last_hash
            last_hash = hash
            buf[4 + i * 4 + 0] = diff & 0xFF
            buf[4 + i * 4 + 1] = (diff >> 8) & 0xFF
            buf[4 + i * 4 + 2] = (diff >> 16) & 0xFF
            buf[4 + i * 4 + 3] = (diff >> 24) & 0xFF
            i += 1

    return out


def encode_fingerprint(hashes, int version, bint signed = 0):
    if isinstance(hashes, list):
        return encode_fingerprint_list(hashes, version, signed)
    else:
        return encode_fingerprint_array(hashes, version, signed)


def decode_fingerprint(bytes inp, bint signed = 0):
    cdef uint32_t hash, last_hash, diff
    cdef int num_hashes
    cdef int version
    cdef array.array hashes
    cdef bint to_signed = signed

    num_hashes = (len(inp) - 4) // 4
    if num_hashes < 0:
        raise ValueError("Invalid fingerprint")

    cdef uint8_t* buf = <uint8_t *>PyBytes_AsString(inp)

    if buf[0] != MAGIC_B0 or buf[1] != MAGIC_B1:
        raise ValueError("Invalid fingerprint magic")

    if buf[2] != FORMAT_VERSION:
        raise ValueError("Invalid format version")

    version = buf[3]

    if to_signed:
        hashes = array.array('i', [])
    else:
        hashes = array.array('I', [])
    array.resize(hashes, num_hashes)

    if hashes.itemsize != 4:
        raise TypeError("Invalid hashes array, need 32-bit items")

    if to_signed:
        last_hash = 0
        for i in range(num_hashes):
            diff = (buf[4 + 4 * i + 0] |
                    (buf[4 + 4 * i + 1] << 8) |
                    (buf[4 + 4 * i + 2] << 16) |
                    (buf[4 + 4 * i + 3] << 24))
            hash = last_hash ^ diff
            hashes.data.as_ints[i] = hash
            last_hash = hash
    else:
        last_hash = 0
        for i in range(num_hashes):
            diff = (buf[4 + 4 * i + 0] |
                    (buf[4 + 4 * i + 1] << 8) |
                    (buf[4 + 4 * i + 2] << 16) |
                    (buf[4 + 4 * i + 3] << 24))
            hash = last_hash ^ diff
            hashes.data.as_uints[i] = hash
            last_hash = hash

    return hashes, version
