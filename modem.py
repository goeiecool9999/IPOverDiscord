import struct
from asyncio import Event

from discord import AudioSource, AudioSink
from math import sin, pi

samples_per_half_symbol = 200

samples_per_ifg = 50


class Encoder(AudioSource):
    def __init__(self):
        self.byte_source = bytes()
        self.byte_index = 0
        self.bit_index = 0
        self.bit_samples = 0
        self.ifg_samples = 0
        self.emitted_event = Event()
        self.emitted_event.set()
        pass

    def set_bytes_to_play(self, in_bytes):
        self.byte_source = bytes([0xaa, 0xaa, 0xaa, 0xaa, 0xaa, 0xaa, 0xab]) + in_bytes
        self.byte_index = 0
        self.bit_index = 0
        self.emitted_event.clear()

    def is_opus(self):
        return False

    def read(self):
        values = bytes()
        for i in range(48 * 20):
            #run out of bytes
            if self.byte_index >= len(self.byte_source):
                if not self.emitted_event.is_set():
                    self.ifg_samples = samples_per_ifg
                self.emitted_event.set()

            sample = 0

            if self.ifg_samples:
                self.ifg_samples -= 1
            elif not self.emitted_event.is_set():
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


            sample = struct.pack('<h', sample)
            values += sample
            values += sample

        return values


class Decoder(AudioSink):

    def __init__(self, data_fun):
        self.high = False
        self.previous_high = False
        self.handle_data = data_fun
        self.current_packet = bytearray()
        self.current_byte = 0
        self.current_bit = 0
        self.samples_last_symbol = 0
        self.finding_sym = False

    def push_bit(self, bit):
        self.current_byte |= bit << self.current_bit
        self.current_bit += 1
        if self.current_bit > 7:
            print(chr(self.current_byte), end='')
            self.current_bit = 0
            self.current_byte = 0
            self.current_packet.append(self.current_byte)
        pass

    def write(self, data):
        unpacked = struct.iter_unpack('<h', data.data)
        samples = [sample[0] for sample in unpacked]

        for sample in samples[::2]:
            self.samples_last_symbol += 1

            if abs(sample) < 100:
                continue
            if self.samples_last_symbol < 10:
                continue
            if self.samples_last_symbol < samples_per_half_symbol*2*.75:
                continue

            self.high = sample > 0

            if not self.finding_sym:
                self.previous_high = self.high
                self.finding_sym = True

            if self.high != self.previous_high:
                self.push_bit(1 if self.high else 0)
                self.samples_last_symbol = 0
                self.finding_sym = False

            self.previous_high = self.high
