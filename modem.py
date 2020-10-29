import queue
import struct
from discord import AudioSource, AudioSink

samples_per_half_symbol = 15

samples_per_ifg = samples_per_half_symbol*16


class Encoder(AudioSource):
    def __init__(self):
        self.packet_buffer = queue.Queue(maxsize=1)
        self.byte_source = bytes()
        self.byte_index = 0
        self.bit_index = 0
        self.bytes_available = False
        self.bit_samples = 0
        self.ifg_samples = 0
        pass

    def set_bytes_to_play(self, in_bytes):
        self.packet_buffer.put(bytes([0x55, 0x55, 0x55, 0x55, 0x55, 0x55, 0xd5]) + in_bytes)

    def is_opus(self):
        return False

    def read(self):
        values = bytes()
        for i in range(48 * 20):
            if not self.packet_buffer.empty() and not self.bytes_available:
                self.byte_source = self.packet_buffer.get(block=False)
                print("??????????????????")
                self.byte_index = 0
                self.bit_index = 0
                self.bytes_available = True

            # run out of bytes
            if self.byte_index >= len(self.byte_source):
                if self.bytes_available:
                    print("!!!!!!!!!!!!!!!!!!!!!")
                    self.ifg_samples = samples_per_ifg
                self.bytes_available = False

            sample = 0

            if self.ifg_samples > 0:
                self.ifg_samples -= 1
            elif self.bytes_available:
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
        self.handle_data = data_fun

        self.high = False
        self.previous_high = False

        self.current_packet = bytearray()
        self.current_byte = 0
        self.current_bit = 0
        self.samples_last_symbol = 0
        self.finding_sym = False

        self.preamble_done = False
        self.last_preamble_bit = 0
        self.was_preamble_inverted = False
        self.preamble_ignore_bits = 2

    def reset(self):
        self.high = False
        self.previous_high = False

        self.current_packet = bytearray()
        self.current_byte = 0
        self.current_bit = 0
        self.samples_last_symbol = 0
        self.finding_sym = False

        self.preamble_done = False
        self.last_preamble_bit = 0
        self.was_preamble_inverted = False
        self.preamble_ignore_bits = 2

    def push_bit(self, bit):
        if not self.preamble_done:
            if self.preamble_ignore_bits:
                self.preamble_ignore_bits -= 1
                return

            # detect end of preamble bit pattern
            self.current_byte >>= 1
            self.current_byte |= bit << 7

            if self.current_byte == 0x2a:
                self.preamble_done = True
                self.was_preamble_inverted = True
            elif self.current_byte == 0xd5:
                self.preamble_done = True

            if self.preamble_done:
                self.current_byte = 0
        else:
            if self.was_preamble_inverted:
                bit = not bit

            self.current_byte |= bit << self.current_bit
            self.current_bit += 1
            if self.current_bit > 7:
                self.current_packet.append(self.current_byte)
                self.current_bit = 0
                self.current_byte = 0

    def write(self, data):
        unpacked = struct.iter_unpack('<h', data.data)
        samples = [sample[0] for sample in unpacked]

        for sample in samples[::2]:
            self.samples_last_symbol += 1

            if self.preamble_done and self.samples_last_symbol > samples_per_half_symbol*8:
                self.handle_data(bytes(self.current_packet))
                self.reset()

            if abs(sample) < 300:
                continue
            if self.samples_last_symbol < 10:
                continue
            if self.samples_last_symbol < samples_per_half_symbol * 2 * .75:
                continue

            self.high = sample > 0

            if not self.finding_sym:
                self.previous_high = self.high
                self.finding_sym = True

            if self.high != self.previous_high:
                self.push_bit(1 if self.high else 0)

                if self.samples_last_symbol >= samples_per_half_symbol*2*2:
                    self.handle_data(bytes(self.current_packet))
                    self.reset()

                self.samples_last_symbol = 0
                self.finding_sym = False

            self.previous_high = self.high
