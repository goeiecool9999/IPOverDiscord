import struct

from discord import AudioSource
from math import sin, pi


class Modem(AudioSource):
    def __init__(self):
        self.byte_source = bytes()
        self.byte_index = 0
        self.bit_index = 0
        self.bit_samples = 0
        self.samples_per_half_symbol = 20
        pass

    def set_bytes_to_play(self, bytes):
        self.byte_source = bytes
        self.byte_index = 0
        self.bit_index = 0

    def is_opus(self):
        return False

    def read(self):
        values = bytes()
        for i in range(48 * 20):
            sample = 3000
            if self.byte_source[self.byte_index] & (1 << self.bit_index):
                sample *= -1

            if self.bit_samples >= self.samples_per_half_symbol:
                sample *= -1

            self.bit_samples += 1
            if self.bit_samples > self.samples_per_half_symbol*2:
                self.bit_samples = 0
                self.bit_index += 1
                if self.bit_index >= 8:
                    self.byte_index += 1
                    self.bit_index = 0
            if self.byte_index >= len(self.byte_source):
                break

            sample = struct.pack('<h', sample)
            values += sample
            values += sample

        if len(values) < 48*20*2:
            values += [0 for i in range(values - 48*20)]

        return values
