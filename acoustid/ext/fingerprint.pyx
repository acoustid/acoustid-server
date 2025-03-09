# cython: language_level=3

import cython
from libc.stdlib cimport malloc, free
from cpython.bytes cimport PyBytes_FromStringAndSize, PyBytes_AS_STRING

STUFF = "Hi"

# Constants
DEF MAGIC = (ord('F') << 0) | (ord('p') << 8)
DEF FORMAT = 1

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


@cython.boundscheck(False)
@cython.wraparound(False)
def encode_fingerprint(list hashes, int version):
    """Encode a fingerprint into a binary format without compression."""
    cdef int i, n
    cdef unsigned int last_hash, current_hash, diff
    cdef char *buffer
    
    n = len(hashes)
    # 4 bytes per hash + 4 bytes header
    cdef int buffer_size = 4 + (n * 4)
    
    # Create Python bytes object with the right size
    # PyBytes_FromStringAndSize allocates the memory and returns a Python object
    py_result = PyBytes_FromStringAndSize(NULL, buffer_size)
    
    # Get a pointer to the buffer inside the bytes object
    buffer = PyBytes_AS_STRING(py_result)
    
    # Write header (little-endian)
    buffer[0] = MAGIC & 0xFF
    buffer[1] = (MAGIC >> 8) & 0xFF
    buffer[2] = FORMAT
    buffer[3] = version
    
    # Compute diffs and write them to buffer
    last_hash = 0
    for i in range(n):
        current_hash = hashes[i] & 0xFFFFFFFF
        diff = current_hash ^ last_hash
        
        # Write diff as 4 bytes (little-endian)
        buffer[4 + i*4] = diff & 0xFF
        buffer[4 + i*4 + 1] = (diff >> 8) & 0xFF
        buffer[4 + i*4 + 2] = (diff >> 16) & 0xFF
        buffer[4 + i*4 + 3] = (diff >> 24) & 0xFF
        
        last_hash = current_hash
    
    return py_result


@cython.boundscheck(False)
@cython.wraparound(False)
def decode_fingerprint(bytes data):
    """Decode a fingerprint from binary format without decompression.
    
    Args:
        data: Raw bytes containing the header and diff data.
        
    Returns:
        Tuple containing a list of integer hash values and the version.
    """
    cdef int i, n, magic, fmt, version, current_hash
    cdef unsigned int diff, last_hash
    cdef char *buffer = PyBytes_AS_STRING(data)
    cdef int buffer_size = len(data)
    
    if buffer_size < 4:
        raise ValueError("Invalid fingerprint data: too short")
    
    # Read header (little-endian)
    magic = buffer[0] | (buffer[1] << 8)
    fmt = buffer[2]
    version = buffer[3]
    
    if magic != MAGIC:
        raise ValueError(f"Invalid fingerprint magic: {magic:#x}, expected: {MAGIC:#x}")
    if fmt != FORMAT:
        raise ValueError(f"Invalid format version: {fmt}, expected: {FORMAT}")
    
    # Calculate number of hashes
    n = (buffer_size - 4) // 4
    
    # Create list to store hashes
    hashes = [0] * n
    
    # Reconstruct hashes from diffs
    last_hash = 0
    for i in range(n):
        # Read diff as 4 bytes (little-endian)
        diff = (cython.uint(buffer[4 + i*4]) |
                (cython.uint(buffer[4 + i*4 + 1]) << 8) |
                (cython.uint(buffer[4 + i*4 + 2]) << 16) |
                (cython.uint(buffer[4 + i*4 + 3]) << 24))
        
        last_hash = diff ^ last_hash
        current_hash = last_hash
        print('decode', i, current_hash)

        hashes[i] = current_hash
    
    return hashes, version
