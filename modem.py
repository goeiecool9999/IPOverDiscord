import struct

from discord import AudioSource
from math import sin, pi


class Modem(AudioSource):
    def __init__(self):
        self.sinewavei = 0
        pass

    def is_opus(self):
        return False

    def read(self):
        values = bytes()
        for i in range(48 * 20 * 2):
            samplenumber = self.sinewavei + i // 2
            sample = sin(samplenumber / 48000 * 2 * pi * 300) * 3000
            sample = int(sample)
            enc = struct.pack('<h', sample)
            values += enc

        return values
