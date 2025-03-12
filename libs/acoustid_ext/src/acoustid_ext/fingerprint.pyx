import cython

from cpython cimport array
from cpython.bytes cimport PyBytes_AsString, PyBytes_FromStringAndSize
from libc.stdint cimport int32_t, uint8_t, uint32_t

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


# Chromaprint integration
cdef extern from "chromaprint.h":
    int chromaprint_decode_fingerprint(
        const char* fingerprint, 
        int size, 
        int32_t** fp, 
        int* length, 
        int* algorithm, 
        int base64
    )
    
    int chromaprint_encode_fingerprint(
        const int32_t* fp, 
        int size, 
        int algorithm, 
        char** encoded_fp, 
        int* encoded_size, 
        int base64
    )
    
    void chromaprint_dealloc(void* ptr)


cdef uint8_t MAGIC_B0 = ord('F')
cdef uint8_t MAGIC_B1 = ord('p')

cdef uint8_t FORMAT_VERSION = 1


ctypedef int32_t true_type
ctypedef uint32_t false_type


ctypedef fused array_type:
    array.array
    list


ctypedef fused signed_type:
    true_type
    false_type


cdef encode_fingerprint_impl(array_type hashes, int version, signed_type signed_flag):
    if hashes is None:
        raise TypeError('hashes cannot be None')

    if array_type is array.array:
        if hashes.ob_descr.itemsize != 4:
            raise TypeError('hashes array must have 32bit items')
        if hashes.ob_descr.typecode not in (b'i', b'I'):
           raise TypeError("hashes array must have typecode 'i' or 'I'")

    cdef uint32_t hash, last_hash, diff
    cdef int i, num_hashes = len(hashes)

    out = PyBytes_FromStringAndSize(NULL, 4 + num_hashes * 4)
    cdef uint8_t* buf = <uint8_t *>PyBytes_AsString(out)

    with cython.nogil(array_type is not list):
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
    cdef int i, num_hashes
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

    with cython.nogil:
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


# New legacy chromaprint functions
class FingerprintError(Exception):
    """Raised when a call to the underlying library fails."""
    pass


cdef decode_legacy_fingerprint_impl(bytes data, bint base64, signed_type signed_flag):
    """Implementation of decode_legacy_fingerprint for different signedness."""
    cdef int32_t *result_ptr = NULL
    cdef int result_size = -1
    cdef int version = -1
    
    cdef array.array hashes
    
    cdef int res = chromaprint_decode_fingerprint(
        data, len(data),
        &result_ptr, &result_size,
        &version, 1 if base64 else 0
    )
    if res != 1:
        raise FingerprintError("Decoding failed")
    if version == -1:
        raise FingerprintError("Algorithm not detected")
    if result_size == -1:
        raise FingerprintError("Invalid fingerprint")
    
    # Create array.array directly with the correct size and type
    if signed_type is true_type:
        hashes = array.array('i', [])
    else:
        hashes = array.array('I', [])
    array.resize(hashes, result_size)
    
    # Copy data directly from C array to array.array
    with cython.nogil:
        for i in range(result_size):
            if signed_type is true_type:
                hashes.data.as_ints[i] = result_ptr[i]
            else:
                hashes.data.as_uints[i] = result_ptr[i]
    
    chromaprint_dealloc(result_ptr)
    return Fingerprint(hashes, version)


def decode_legacy_fingerprint(bytes data, bint base64=True, bint signed=False):
    """Decode a chromaprint fingerprint from a byte string.
    
    Args:
        data: The encoded fingerprint as bytes
        base64: Whether the fingerprint is base64 encoded
        signed: Whether to interpret the hash values as signed integers
        
    Returns:
        Fingerprint object containing the hash values and algorithm version
    """
    if signed:
        return decode_legacy_fingerprint_impl(data, base64, <true_type>1)
    else:
        return decode_legacy_fingerprint_impl(data, base64, <false_type>0)


cdef encode_legacy_fingerprint_array_impl(array.array fingerprint, int version, bint base64, signed_type signed_flag):
    """Optimized implementation for array.array inputs that avoids extra allocation."""
    if fingerprint.ob_descr.itemsize != 4:
        raise TypeError('fingerprint array must have 32bit items')
    if fingerprint.ob_descr.typecode not in (b'i', b'I'):
        raise TypeError("fingerprint array must have typecode 'i' or 'I'")

    cdef int32_t *fp_ptr = <int32_t*>fingerprint.data.as_ints
    cdef int size = len(fingerprint)
    cdef char *result_ptr = NULL
    cdef int result_size = 0
    
    cdef int res = chromaprint_encode_fingerprint(
        fp_ptr, size, version,
        &result_ptr, &result_size,
        1 if base64 else 0
    )
    if res != 1:
        raise FingerprintError("Encoding failed")

    # Convert C string to Python bytes
    result = result_ptr[:result_size]
    chromaprint_dealloc(result_ptr)
    return result


cdef encode_legacy_fingerprint_list_impl(list fingerprint, int version, bint base64, signed_type signed_flag):
    """Implementation for list inputs that converts to array.array and reuses array implementation."""
    cdef array.array temp_array
    
    # Create array.array with proper type based on signed flag
    if signed_type is true_type:
        temp_array = array.array('i', fingerprint)
    else:
        temp_array = array.array('I', fingerprint)
    
    # Reuse the array implementation
    return encode_legacy_fingerprint_array_impl(temp_array, version, base64, signed_flag)


def encode_legacy_fingerprint(object fingerprint, int version, bint base64=True, bint signed=False):
    """Encode a chromaprint fingerprint to a byte string.
    
    Args:
        fingerprint: List or array.array of integer hash values
        version: The algorithm version
        base64: Whether to base64 encode the output
        signed: Whether the hash values are signed integers
        
    Returns:
        Encoded fingerprint as bytes
    """
    if isinstance(fingerprint, list):
        if signed:
            return encode_legacy_fingerprint_list_impl(<list>fingerprint, version, base64, <true_type>1)
        else:
            return encode_legacy_fingerprint_list_impl(<list>fingerprint, version, base64, <false_type>0)
    elif isinstance(fingerprint, array.array):
        if signed:
            return encode_legacy_fingerprint_array_impl(<array.array>fingerprint, version, base64, <true_type>1)
        else:
            return encode_legacy_fingerprint_array_impl(<array.array>fingerprint, version, base64, <false_type>0)
    else:
        raise TypeError("Invalid fingerprint, must be list or array.array")