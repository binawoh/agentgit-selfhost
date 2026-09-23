"""Reject architecture or dynamic-runtime regressions in distributable binaries."""

import struct
import unittest

from pack import validate_binary


def elf(machine, kind=1, dynamic_tag=0):
    binary = bytearray(136)
    binary[:6] = b"\x7fELF\x02\x01"
    struct.pack_into("<H", binary, 18, machine)
    struct.pack_into("<Q", binary, 32, 64)
    struct.pack_into("<HH", binary, 54, 56, 1)
    struct.pack_into("<IIQQQQQQ", binary, 64, kind, 0, 120, 0, 0, 16, 16, 8)
    struct.pack_into("<qQ", binary, 120, dynamic_tag, 0)
    return binary


class BinaryValidation(unittest.TestCase):
    def test_static_architectures_and_static_pie(self):
        validate_binary(elf(62), "x64")
        validate_binary(elf(183), "arm64")
        validate_binary(elf(62, kind=2), "x64")

    def test_wrong_architecture(self):
        with self.assertRaises(ValueError):
            validate_binary(elf(62), "arm64")

    def test_dynamic_interpreter_or_dependency(self):
        for binary in [elf(62, kind=3), elf(62, kind=2, dynamic_tag=1)]:
            with self.assertRaises(ValueError):
                validate_binary(binary, "x64")

    def test_truncated_headers(self):
        for binary in [b"", elf(62)[:100], elf(62, kind=2)[:125]]:
            with self.assertRaises(ValueError):
                validate_binary(binary, "x64")


if __name__ == "__main__":
    unittest.main()
