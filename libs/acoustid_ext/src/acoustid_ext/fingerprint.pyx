import cython

from cpython cimport array
from cpython.bytes cimport PyBytes_AsString, PyBytes_FromStringAndSize
from cpython.unicode cimport PyUnicode_AsUTF8String, PyUnicode_FromStringAndSize
from libc.math cimport abs
from libc.stdint cimport int32_t, uint8_t, uint32_t, uint64_t

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
    ) nogil noexcept
    
    int chromaprint_encode_fingerprint(
        const int32_t* fp, 
        int size, 
        int algorithm, 
        char** encoded_fp, 
        int* encoded_size, 
        int base64
    ) nogil noexcept
    
    void chromaprint_dealloc(void* ptr)


ctypedef int32_t true_type
ctypedef uint32_t false_type


ctypedef fused array_type:
    array.array
    list


ctypedef fused signed_type:
    true_type
    false_type


cdef extern from *:
    """
    #include <endian.h>

    #if __BYTE_ORDER == __LITTLE_ENDIAN
    #define IS_LITTLE_ENDIAN 1
    #else
    #define IS_LITTLE_ENDIAN 0
    #endif

    #define MAGIC_B0 'F'
    #define MAGIC_B1 'p'
    #define FORMAT_VERSION 1

    """

    int IS_LITTLE_ENDIAN

    int MAGIC_B0
    int MAGIC_B1
    int FORMAT_VERSION


cdef inline uint32_t byteswap_uint32(uint32_t value) noexcept nogil:
    cdef uint32_t b0 = (value & 0xFFu) << 24
    cdef uint32_t b1 = (value & 0xFF00u) << 8
    cdef uint32_t b2 = (value & 0xFF0000u) >> 8
    cdef uint32_t b3 = (value & 0xFF000000u) >> 24
    return b0 | b1 | b2 | b3


@cython.boundscheck(False)
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
    cdef uint8_t* buf_byte = <uint8_t*>PyBytes_AsString(out)
    cdef uint32_t* buf_word = <uint32_t*>(buf_byte + 4)  # uint32_t pointer to diff array portion

    with cython.nogil(array_type is not list):
        # Write header bytes
        buf_byte[0] = MAGIC_B0
        buf_byte[1] = MAGIC_B1
        buf_byte[2] = FORMAT_VERSION
        buf_byte[3] = version

        last_hash = 0
        i = 0
        while i < num_hashes:
            if array_type is list:
                if signed_type is true_type:
                    hash = <uint32_t>(<int>hashes[i])
                else:
                    hash = hashes[i]
            else:
                hash = hashes.data.as_uints[i]

            diff = hash ^ last_hash
            last_hash = hash

            if IS_LITTLE_ENDIAN:
                # Direct write on little-endian platforms
                buf_word[i] = diff
            else:
                # Byte swap on big-endian platforms
                buf_word[i] = byteswap_uint32(diff)

            i += 1

    return out


@cython.boundscheck(False)
cdef decode_fingerprint_impl(bytes inp, signed_type signed_flag):
    cdef uint32_t hash, last_hash, diff
    cdef int i, num_hashes
    cdef int version
    cdef array.array hashes

    if inp is None:
        raise TypeError('inp cannot be None')

    num_hashes = (len(inp) - 4) // 4
    if num_hashes < 0:
        raise ValueError("Invalid fingerprint")

    cdef uint8_t* buf_byte = <uint8_t*>PyBytes_AsString(inp)
    cdef uint32_t* buf_word = <uint32_t*>(buf_byte + 4)  # uint32_t pointer to diff array portion

    if buf_byte[0] != MAGIC_B0 or buf_byte[1] != MAGIC_B1:
        raise ValueError("Invalid fingerprint magic")

    if buf_byte[2] != FORMAT_VERSION:
        raise ValueError("Invalid format version")

    version = buf_byte[3]

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
            if IS_LITTLE_ENDIAN:
                # Direct read on little-endian platforms
                diff = buf_word[i]
            else:
                # Byte swap on big-endian platforms
                diff = byteswap_uint32(buf_word[i])

            hash = last_hash ^ diff
            hashes.data.as_uints[i] = hash
            last_hash = hash

    return Fingerprint(hashes, version)


@cython.boundscheck(False)
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


@cython.boundscheck(False)
def decode_fingerprint(bytes inp, bint signed = 0):
    if signed:
        return decode_fingerprint_impl(inp, <true_type>1)
    else:
        return decode_fingerprint_impl(inp, <false_type>0)


# New legacy chromaprint functions
class FingerprintError(Exception):
    """Raised when a call to the underlying library fails."""
    pass


def decode_legacy_fingerprint(object data, bint base64=True, bint signed=False):
    """Decode a chromaprint fingerprint from a byte string.
    
    Args:
        data: The encoded fingerprint as bytes | str (depending on base64)
        base64: Whether the fingerprint is base64 encoded
        signed: Whether to interpret the hash values as signed integers
        
    Returns:
        Fingerprint object containing the hash values and algorithm version
    """

    cdef bytes data_as_bytes

    if isinstance(data, str) and base64:
        data_as_bytes = PyUnicode_AsUTF8String(data)
    elif isinstance(data, bytes):
        data_as_bytes = data
    else:
        if base64:
            raise TypeError("Invalid data, must be str or bytes")
        else:
            raise TypeError("Invalid data, must be bytes")

    cdef int32_t *result_ptr = NULL
    cdef int result_size = -1
    cdef int version = -1
    cdef array.array hashes
    cdef int res

    cdef char *data_ptr = <char*>PyBytes_AsString(data_as_bytes)
    cdef int data_size = len(data_as_bytes)

    try:
        with cython.nogil:
            res = chromaprint_decode_fingerprint(
                data_ptr, data_size,
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
        hashes = array.array('i' if signed else 'I', [])
        array.resize(hashes, result_size)
        
        # Copy data directly from C array to array.array
        with cython.nogil:
            for i in range(result_size):
                hashes.data.as_ints[i] = result_ptr[i]

        return Fingerprint(hashes, version)
    finally:
        if result_ptr != NULL:
            chromaprint_dealloc(result_ptr)


def encode_legacy_fingerprint(object hashes, int version, bint base64=True, bint signed=False):
    """Encode a chromaprint fingerprint to a byte string.
    
    Args:
        hashes: List or array.array of integer hash values
        version: The algorithm version
        base64: Whether to base64 encode the output
        signed: Whether the hash values are signed integers
        
    Returns:
        Encoded fingerprint as bytes or str, depending on base64
    """

    cdef array.array hashes_as_array

    if isinstance(hashes, list):
        if signed:
            hashes_as_array = array.array('i', hashes)
        else:
            hashes_as_array = array.array('I', hashes)
    elif isinstance(hashes, array.array):
        if hashes.ob_descr.itemsize != 4:
            raise TypeError('hashes array must have 32bit items')
        if hashes.ob_descr.typecode != ('i' if signed else 'I'):
            raise TypeError("hashes array must have typecode 'i' or 'I'")          
        hashes_as_array = hashes
    else:
        raise TypeError("Invalid hashes, must be list or array.array")

    cdef int32_t *hashes_ptr = <int32_t*>hashes_as_array.data.as_ints
    cdef int hashes_size = len(hashes_as_array)
    cdef char *result_ptr = NULL
    cdef int result_size = 0
    cdef int res

    try:
        with cython.nogil:
            res = chromaprint_encode_fingerprint(
                hashes_ptr, hashes_size, version,
                &result_ptr, &result_size,
                1 if base64 else 0
            )
        if res != 1:
            raise FingerprintError("Encoding failed")

        if base64:
            return PyUnicode_FromStringAndSize(result_ptr, result_size)
        else:
            return PyBytes_FromStringAndSize(result_ptr, result_size)

    finally:
        if result_ptr != NULL:
            chromaprint_dealloc(result_ptr)


@cython.boundscheck(False)
@cython.wraparound(False)
def simhash(array.array hashes, bint signed = False):
    """
    Compute SimHash of a set of fingerprint hashes.

    Args:
        hashes: An array.array of 32-bit unsigned integers representing fingerprint hashes
        signed: Whether the result should be signed or unsigned
        
    Returns:
        A 32-bit signed or unsigned integer SimHash value
    """
    if hashes.typecode not in ('I', 'i'):
        raise TypeError("features must be an array of integers")
        
    cdef int i, j, n
    cdef uint32_t h
    cdef uint32_t[32] v
    cdef uint32_t result = 0
    
    n = len(hashes)

    with nogil:
        # Initialize vector
        for i in range(32):
            v[i] = 0

        # Compute aggregated bit counts for each bit position
        for i in range(n):
            h = hashes.data.as_uints[i]
            for j in range(32):
                v[j] += (h >> j) & 1

        # Compute final SimHash value
        for i in range(32):
            if v[i] > n / 2:
                result |= (1 << i)

    if signed:
        return <int32_t>result
    else:
        return result
