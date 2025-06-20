#  Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
#  See https://llvm.org/LICENSE.txt for license information.
#  SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception

import numpy as np
import ctypes

try:
    import ml_dtypes
except ModuleNotFoundError:

    ml_dtypes = None

class C128(ctypes.Structure):
    """A ctype representation for MLIR's Double Complex."""

    _fields_ = [("real", ctypes.c_double), ("imag", ctypes.c_double)]

class C64(ctypes.Structure):
    """A ctype representation for MLIR's Float Complex."""

    _fields_ = [("real", ctypes.c_float), ("imag", ctypes.c_float)]

class F16(ctypes.Structure):
    """A ctype representation for MLIR's Float16."""

    _fields_ = [("f16", ctypes.c_int16)]

class BF16(ctypes.Structure):
    """A ctype representation for MLIR's BFloat16."""

    _fields_ = [("bf16", ctypes.c_int16)]

class F8E5M2(ctypes.Structure):
    """A ctype representation for MLIR's Float8E5M2."""

    _fields_ = [("f8E5M2", ctypes.c_int8)]

def as_ctype(dtp):
    """Converts dtype to ctype."""
    if dtp == np.dtype(np.complex128):
        return C128
    if dtp == np.dtype(np.complex64):
        return C64
    if dtp == np.dtype(np.float16):
        return F16
    if ml_dtypes is not None and dtp == ml_dtypes.bfloat16:
        return BF16
    if ml_dtypes is not None and dtp == ml_dtypes.float8_e5m2:
        return F8E5M2
    return np.ctypeslib.as_ctypes_type(dtp)

def to_numpy(array):
    """Converts ctypes array back to numpy dtype array."""
    if array.dtype == C128:
        return array.view("complex128")
    if array.dtype == C64:
        return array.view("complex64")
    if array.dtype == F16:
        return array.view("float16")
    assert not (
        array.dtype == BF16 and ml_dtypes is None
    ), f"bfloat16 requires the ml_dtypes package, please run:\n\npip install ml_dtypes\n"
    if array.dtype == BF16:
        return array.view("bfloat16")
    assert not (
        array.dtype == F8E5M2 and ml_dtypes is None
    ), f"float8_e5m2 requires the ml_dtypes package, please run:\n\npip install ml_dtypes\n"
    if array.dtype == F8E5M2:
        return array.view("float8_e5m2")
    return array

def make_nd_memref_descriptor(rank, dtype):
    class MemRefDescriptor(ctypes.Structure):
        """Builds an empty descriptor for the given rank/dtype, where rank>0."""

        _fields_ = [
            ("allocated", ctypes.c_longlong),
            ("aligned", ctypes.POINTER(dtype)),
            ("offset", ctypes.c_longlong),
            ("shape", ctypes.c_longlong * rank),
            ("strides", ctypes.c_longlong * rank),
        ]

    return MemRefDescriptor

def make_zero_d_memref_descriptor(dtype):
    class MemRefDescriptor(ctypes.Structure):
        """Builds an empty descriptor for the given dtype, where rank=0."""

        _fields_ = [
            ("allocated", ctypes.c_longlong),
            ("aligned", ctypes.POINTER(dtype)),
            ("offset", ctypes.c_longlong),
        ]

    return MemRefDescriptor

class UnrankedMemRefDescriptor(ctypes.Structure):
    """Creates a ctype struct for memref descriptor"""

    _fields_ = [("rank", ctypes.c_longlong), ("descriptor", ctypes.c_void_p)]

def get_ranked_memref_descriptor(nparray):
    """Returns a ranked memref descriptor for the given numpy array."""
    ctp = as_ctype(nparray.dtype)
    if nparray.ndim == 0:
        x = make_zero_d_memref_descriptor(ctp)()
        x.allocated = nparray.ctypes.data
        x.aligned = nparray.ctypes.data_as(ctypes.POINTER(ctp))
        x.offset = ctypes.c_longlong(0)
        return x

    x = make_nd_memref_descriptor(nparray.ndim, ctp)()
    x.allocated = nparray.ctypes.data
    x.aligned = nparray.ctypes.data_as(ctypes.POINTER(ctp))
    x.offset = ctypes.c_longlong(0)
    x.shape = nparray.ctypes.shape

    strides_ctype_t = ctypes.c_longlong * nparray.ndim
    x.strides = strides_ctype_t(*[x // nparray.itemsize for x in nparray.strides])
    return x

def get_unranked_memref_descriptor(nparray):
    """Returns a generic/unranked memref descriptor for the given numpy array."""
    d = UnrankedMemRefDescriptor()
    d.rank = nparray.ndim
    x = get_ranked_memref_descriptor(nparray)
    d.descriptor = ctypes.cast(ctypes.pointer(x), ctypes.c_void_p)
    return d

def move_aligned_ptr_by_offset(aligned_ptr, offset):
    """Moves the supplied ctypes pointer ahead by `offset` elements."""
    aligned_addr = ctypes.addressof(aligned_ptr.contents)
    elem_size = ctypes.sizeof(aligned_ptr.contents)
    shift = offset * elem_size
    content_ptr = ctypes.cast(aligned_addr + shift, type(aligned_ptr))
    return content_ptr

def unranked_memref_to_numpy(unranked_memref, np_dtype):
    """Converts unranked memrefs to numpy arrays."""
    ctp = as_ctype(np_dtype)
    descriptor = make_nd_memref_descriptor(unranked_memref[0].rank, ctp)
    val = ctypes.cast(unranked_memref[0].descriptor, ctypes.POINTER(descriptor))
    content_ptr = move_aligned_ptr_by_offset(val[0].aligned, val[0].offset)
    np_arr = np.ctypeslib.as_array(content_ptr, shape=val[0].shape)
    strided_arr = np.lib.stride_tricks.as_strided(
        np_arr,
        np.ctypeslib.as_array(val[0].shape),
        np.ctypeslib.as_array(val[0].strides) * np_arr.itemsize,
    )
    return to_numpy(strided_arr)

def ranked_memref_to_numpy(ranked_memref):
    """Converts ranked memrefs to numpy arrays."""
    content_ptr = move_aligned_ptr_by_offset(
        ranked_memref[0].aligned, ranked_memref[0].offset
    )
    np_arr = np.ctypeslib.as_array(content_ptr, shape=ranked_memref[0].shape)
    strided_arr = np.lib.stride_tricks.as_strided(
        np_arr,
        np.ctypeslib.as_array(ranked_memref[0].shape),
        np.ctypeslib.as_array(ranked_memref[0].strides) * np_arr.itemsize,
    )
    return to_numpy(strided_arr)