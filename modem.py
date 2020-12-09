import queue
import struct
from concurrent.futures.thread import ThreadPoolExecutor
import time
from itertools import zip_longest

from discord import AudioSource, AudioSink

threadpool = ThreadPoolExecutor(8)
samples_per_half_symbol = 12

samples_per_ifg = samples_per_half_symbol * 2 * 32

enc_table = [
    0b11110,
    0b01001,
    0b10100,
    0b10101,
    0b01010,
    0b01011,
    0b01110,
    0b01111,

    0b10010,
    0b10011,
    0b10110,
    0b10111,
    0b11010,
    0b11011,
    0b11100,
    0b11101,
]

dec_map = {}
for i in range(16):
    dec_map[enc_table[i]] = i

class Encoder():
    def __init__(self):
        self.packet_buffer = queue.Queue(maxsize=1)
        self.byte_source = bytes()
        self.byte_index = 0
        self.bit_index = 0
        self.bytes_available = False
        self.bit_samples = 0
        self.ifg_samples = 0
        self.high = False
        self.transitioned = False
        pass

    def set_bytes_to_play(self, in_bytes):
        self.packet_buffer.put(in_bytes + bytes([0, 0, 0, 0, 0, 0]))

    def read(self):
        values = []
        for i in range(48 * 20):
            if not self.packet_buffer.empty() and not self.bytes_available and self.ifg_samples == 0:
                # encode packet using 4b5b
                self.byte_source = [0x1f,0x1f,0x1f,0x1f,0x1f,0x1f,0x17] + [enc_table[nib] for i in self.packet_buffer.get(block=False) for nib in [i & 0xf, i >> 4]]
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
                sample = 32767

                if self.bit_samples >= samples_per_half_symbol and not self.transitioned and self.byte_source[self.byte_index] & (1 << self.bit_index):
                    self.high = not self.high
                    self.transitioned = True

                if not self.high:
                    sample *= -1

                self.bit_samples += 1
                if self.bit_samples >= samples_per_half_symbol * 2:
                    self.bit_samples = 0
                    self.bit_index += 1
                    self.transitioned = False
                    if self.bit_index >= 5:
                        self.byte_index += 1
                        self.bit_index = 0

            values.append(sample)

        return values


class StereoEncoder(AudioSource):
    def __init__(self):
        self.left_enc = Encoder()
        self.right_enc = Encoder()

    def is_opus(self):
        return False

    def set_bytes_to_play(self, in_bytes):
        if len(in_bytes) % 2 != 0:
            in_bytes = in_bytes + b"\x00"
        self.left_enc.set_bytes_to_play(in_bytes[::2])
        self.right_enc.set_bytes_to_play(in_bytes[1::2])

    def read(self):
        left_chan = threadpool.submit(self.left_enc.read)
        right_chan = threadpool.submit(self.right_enc.read)
        interleave = zip(left_chan.result(), right_chan.result())
        interleave = [struct.pack('<h', num) for elem in interleave for num in elem]

        return bytes().join(interleave)


class Decoder:

    def __init__(self, data_fun, stereodec):
        self.handle_data = data_fun

        self.previous_high = False

        self.current_packet = bytearray()
        self.current_byte = 0
        self.current_code = 0
        self.high_nibble = False
        self.current_bit = 0
        self.samples_last_symbol = 0

        self.preamble_done = False

        self.stereodec = stereodec

    def reset(self):
        self.previous_high = False

        self.current_packet = bytearray()
        self.current_byte = 0
        self.current_code = 0
        self.high_nibble = False
        self.current_bit = 0
        self.samples_last_symbol = 0

        self.preamble_done = False
        print("----------------")

    def push_bit(self, bit):
        if not self.preamble_done:
            # detect end of preamble bit pattern
            self.current_byte >>= 1
            self.current_byte |= bit << 7

            if self.current_byte == 0xbf:
                self.preamble_done = True

            # print('{:08b}'.format(self.current_byte))

            if self.preamble_done:
                self.stereodec.left_has_data = False
                self.stereodec.right_has_data = False
                print("****************")
                self.current_byte = 0
                self.current_code = 0
        else:

            self.current_code |= bit << self.current_bit
            self.current_bit += 1
            if self.current_bit >= 5:
                if not self.high_nibble:
                    try:
                        self.current_byte |= dec_map[self.current_code]
                    except:
                        pass
                    self.high_nibble = True
                else:
                    try:
                        self.current_byte |= dec_map[self.current_code] << 4
                    except:
                        pass
                    self.current_packet.append(self.current_byte)
                    self.current_byte = 0
                    self.high_nibble = False

                self.current_bit = 0
                self.current_code = 0


    def write(self, samples):
        for sample in samples:
            self.samples_last_symbol += 1

            # handle IFG
            if self.preamble_done and self.samples_last_symbol > samples_per_ifg // 2:
                self.handle_data(bytes(self.current_packet))
                self.reset()
                continue

            if abs(sample) < 12000:
                continue

            high = sample > 0
            if high != self.previous_high and self.samples_last_symbol >= samples_per_half_symbol:
                if self.samples_last_symbol < samples_per_half_symbol*2*5:
                    for i in range(int(round(self.samples_last_symbol/(samples_per_half_symbol*2)))-1):
                        self.push_bit(0)
                    self.push_bit(1)
                self.samples_last_symbol = 0

            self.previous_high = high


class StereoDecoder(AudioSink):

    def __init__(self, data_fun):
        self.left_dec = Decoder(lambda data: self.left_data(data), self)
        self.right_dec = Decoder(lambda data: self.right_data(data), self)
        self.left_has_data = False
        self.right_has_data = False
        self.left_bytes = None
        self.right_bytes = None
        self.data_fun = data_fun
        pass

    def submit_data(self):
        print("submitting at: ", int(time.time()))

        # print("left data:")
        # print (''.join('{:02x}'.format(x) for x in self.left_bytes))
        # print("right data:")
        # print (''.join('{:02x}'.format(x) for x in self.right_bytes))

        delta = abs(len(self.left_bytes) - len(self.right_bytes))
        if delta >= 1:
            print("################################################")
            print(delta)
        interleave = zip_longest(self.left_bytes, self.right_bytes, fillvalue=0)
        interleave = [num for elem in interleave for num in elem]
        interleavedbytes = bytes(interleave)

        # print("complete data:")
        # print (''.join('{:02x}'.format(x) for x in interleavedbytes))

        self.data_fun(interleavedbytes)
        self.left_has_data = False
        self.right_has_data = False

    def left_data(self, data):
        print("left received data at: ", int(time.time()))
        self.left_bytes = data
        self.left_has_data = True
        if self.right_has_data:
            self.submit_data()

    def right_data(self, data):
        print("right received data at: ", int(time.time()))
        self.right_bytes = data
        self.right_has_data = True
        if self.left_has_data:
            self.submit_data()

    def write(self, data):
        unpacked = struct.iter_unpack('<h', data.data)
        samples = [sample[0] for sample in unpacked]

        self.left_dec.write(samples[::2])
        self.right_dec.write(samples[1::2])
