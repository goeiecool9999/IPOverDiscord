import struct

from discord import AudioSource, AudioSink
from math import sin, pi

samples_per_half_symbol = 200


class Encoder(AudioSource):
    def __init__(self):
        self.byte_source = bytes()
        self.byte_index = 0
        self.bit_index = 0
        self.bit_samples = 0
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

            if self.bit_samples >= samples_per_half_symbol:
                sample *= -1

            self.bit_samples += 1
            if self.bit_samples > samples_per_half_symbol * 2:
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

        if len(values) < 48 * 20 * 2 * 2:
            values += [0 for i in range(48 * 20 * 2 * 2 - len(values))]

        return values


class Decoder(AudioSink):

    def __init__(self, data_fun):
        self.high = False
        self.previous_high = False
        self.handle_data = data_fun
        self.current_packet = bytes()
        self.current_byte = 0
        self.samples_last_symbol = 0

    def push_bit(self, bit):
        pass

    def write(self, data):
        unpacked = struct.iter_unpack('<h', data.data)
        samples = [sample[0] for sample in unpacked]

        for sample in samples:
            self.samples_last_symbol += 1

            if abs(sample) < 100:
                continue

            self.high = sample > 0

            if self.previous_high != self.high:
                if self.samples_last_symbol < 10:
                    continue
                if self.samples_last_symbol < samples_per_half_symbol * 2 * .75:
                    continue

                print(1 if self.high else 0, end='')

                self.samples_last_symbol = 0

                self.previous_high = self.high
