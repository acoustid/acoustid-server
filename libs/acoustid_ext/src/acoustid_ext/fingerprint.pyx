from cpython cimport array
from cpython.bytes cimport PyBytes_AsString, PyBytes_FromStringAndSize
from libc.stdint cimport uint8_t, uint32_t

import array
from typing import NamedTuple


class Fingerprint(NamedTuple):
    hashes: array.array
    version: int


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


ctypedef int true_type
ctypedef float false_type


ctypedef fused array_type:
    array.array
    list


ctypedef fused signed_type:
    true_type
    false_type


cdef encode_fingerprint_impl(array_type hashes, int version, signed_type signed_flag):
    if hashes is None:
        raise TypeError('hashes cant be None')

    if array_type is array.array:
        if hashes.ob_descr.itemsize != 4:
            raise TypeError('hashes array must have 32bit items')

    cdef uint32_t hash, last_hash, diff
    cdef int i, num_hashes = len(hashes)

    out = PyBytes_FromStringAndSize(NULL, 4 + num_hashes * 4)
    cdef uint8_t* buf = <uint8_t *>PyBytes_AsString(out)

    buf[0] = MAGIC_B0
    buf[1] = MAGIC_B1
    buf[2] = FORMAT_VERSION
    buf[3] = version

    last_hash = 0
    i = 0
    while i < num_hashes:
        if array_type is list:
            if signed_type is true_type:
                hash = <uint32_t>(<int>hashes[i])
            else:
                hash = hashes[i]
        else:
            if signed_type is true_type:
                hash = <uint32_t>(<int>hashes.data.as_ints[i])
            else:
                hash = hashes.data.as_uints[i]
        diff = hash ^ last_hash
        last_hash = hash
        buf[4 + i * 4 + 0] = diff & 0xFF
        buf[4 + i * 4 + 1] = (diff >> 8) & 0xFF
        buf[4 + i * 4 + 2] = (diff >> 16) & 0xFF
        buf[4 + i * 4 + 3] = (diff >> 24) & 0xFF
        i += 1

    return out


cdef decode_fingerprint_impl(bytes inp, signed_type signed_flag):
    cdef uint32_t hash, last_hash, diff
    cdef int num_hashes
    cdef int version
    cdef array.array hashes

    num_hashes = (len(inp) - 4) // 4
    if num_hashes < 0:
        raise ValueError("Invalid fingerprint")

    cdef uint8_t* buf = <uint8_t *>PyBytes_AsString(inp)

    if buf[0] != MAGIC_B0 or buf[1] != MAGIC_B1:
        raise ValueError("Invalid fingerprint magic")

    if buf[2] != FORMAT_VERSION:
        raise ValueError("Invalid format version")

    version = buf[3]

    if signed_type is true_type:
        hashes = array.array('i', [])
    else:
        hashes = array.array('I', [])
    array.resize(hashes, num_hashes)

    if hashes.itemsize != 4:
        raise TypeError("Invalid hashes array, need 32-bit items")

    last_hash = 0
    for i in range(num_hashes):
        diff = (buf[4 + 4 * i + 0] |
                (buf[4 + 4 * i + 1] << 8) |
                (buf[4 + 4 * i + 2] << 16) |
                (buf[4 + 4 * i + 3] << 24))
        hash = last_hash ^ diff
        if signed_type is true_type:
            hashes.data.as_ints[i] = hash
        else:
            hashes.data.as_uints[i] = hash
        last_hash = hash

    return Fingerprint(hashes, version)


def encode_fingerprint(object hashes, int version, bint signed = 0):
    if isinstance(hashes, list):
        if signed:
            return encode_fingerprint_impl(<list>hashes, version, <true_type>1)
        else:
            return encode_fingerprint_impl(<list>hashes, version, <false_type>0)
    elif isinstance(hashes, array.array):
        if signed:
            return encode_fingerprint_impl(<array.array>hashes, version, <true_type>1)
        else:
            return encode_fingerprint_impl(<array.array>hashes, version, <false_type>0)
    else:
        raise TypeError("Invalid hashes array")


def decode_fingerprint(bytes inp, bint signed = 0):
    if signed:
        return decode_fingerprint_impl(inp, <true_type>1)
    else:
        return decode_fingerprint_impl(inp, <false_type>0)
