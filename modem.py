import queue
import struct
from concurrent.futures.thread import ThreadPoolExecutor
import time
from itertools import zip_longest

from discord import AudioSource, AudioSink

import soundcard as sc

threadpool = ThreadPoolExecutor(8)
samples_per_half_symbol = 10

samples_per_ifg = samples_per_half_symbol*2*16


class Encoder():
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
        self.packet_buffer.put(bytes([0x55, 0x55, 0x55, 0x55, 0x55, 0x55, 0xd5]) + in_bytes + bytes([0,0,0,0,0,0,0,0,0,0]))

    def read(self):
        values = []
        for i in range(48 * 20):
            if not self.packet_buffer.empty() and not self.bytes_available and self.ifg_samples == 0:
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
                sample = 32767
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

            values.append(sample)

        return values

class StereoEncoder(AudioSource):
    def __init__(self):
        self.left_enc = Encoder()
        self.right_enc = Encoder()
        pass


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
        interleave = [struct.pack('<h',num) for elem in interleave for num in elem]

        return bytes().join(interleave)



class Decoder:

    def __init__(self, data_fun, stereodec):
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

        self.stereodec = stereodec

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

        print("----------------")

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
                self.stereodec.left_has_data = False
                self.stereodec.right_has_data = False
                print("****************")
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

    def write(self, samples):

        for sample in samples:
            self.samples_last_symbol += 1



            if self.preamble_done and self.samples_last_symbol > samples_per_ifg//2:
                self.handle_data(bytes(self.current_packet))
                self.reset()
                continue

            if abs(sample) < 6000:
                continue
            if self.samples_last_symbol < samples_per_half_symbol * 2 * .75:
                continue

            self.high = sample > 0

            if not self.finding_sym:
                self.previous_high = self.high
                self.finding_sym = True

            if self.high != self.previous_high:
                if self.preamble_done and self.samples_last_symbol > samples_per_ifg//2:
                    self.handle_data(bytes(self.current_packet))
                    self.reset()
                    continue

                self.push_bit(1 if self.high else 0)
                self.samples_last_symbol = 0
                self.finding_sym = False

            self.previous_high = self.high


import numpy as np
class StereoDecoder(AudioSink):

    def __init__(self, data_fun):
        self.left_dec = Decoder(lambda data: self.left_data(data), self)
        self.right_dec = Decoder(lambda data: self.right_data(data), self)
        self.left_has_data = False
        self.right_has_data = False
        self.left_bytes = None
        self.right_bytes = None
        self.data_fun = data_fun
        self.stream = sc.default_speaker().player(samplerate=48000,channels=2,blocksize=960*4)
        self.stream.__enter__();
        pass

    def submit_data(self):
        print ("submitting at: ", int(time.time()))
        print("left data:")
        print (''.join('{:02x}'.format(x) for x in self.left_bytes))
        print("right data:")
        print (''.join('{:02x}'.format(x) for x in self.right_bytes))
        delta = abs(len(self.left_bytes) - len(self.right_bytes))
        if delta >= 1:
            print ("################################################")
            print (delta)
        interleave = zip_longest(self.left_bytes, self.right_bytes, fillvalue=0)
        interleave = [num for elem in interleave for num in elem]
        interleavedbytes = bytes(interleave)
        print("complete data:")
        print (''.join('{:02x}'.format(x) for x in interleavedbytes))
        self.data_fun(interleavedbytes)
        self.left_has_data = False
        self.right_has_data = False

    def left_data(self, data):
        print ("left received data at: ", int(time.time()))
        self.left_bytes = data
        self.left_has_data = True
        if self.right_has_data:
            self.submit_data()

    def right_data(self, data):
        print ("right received data at: ", int(time.time()))
        self.right_bytes = data
        self.right_has_data = True
        if self.left_has_data:
            self.submit_data()

    def write(self, data):
        unpacked = struct.iter_unpack('<h', data.data)
        samples = [sample[0] for sample in unpacked]
        streams = np.reshape(np.int16(samples) / 32767, newshape=(len(samples)//2,2))

        self.stream.play(streams)

        self.left_dec.write(samples[::2])
        self.right_dec.write(samples[1::2])