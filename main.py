import io
import signal
from concurrent.futures.thread import ThreadPoolExecutor

from pytun import TunTapDevice
import discord
from discord.ext import tasks, commands

from threading import Thread
import os

import logging

from buffer import Buffer

logging.basicConfig(level=logging.INFO)

tun = TunTapDevice(name='discip')
tun.addr = os.environ['SRC_IP']
tun.dstaddr = os.environ['DST_IP']
tun.netmask = '255.255.255.0'
tun.mtu = 1500
tun.persist(True)
tun.up()

def terminate():
    tun.down()

signal.signal(signal.SIGINT, terminate)

TOKEN = os.environ["DISCORD_TOKEN"]

bot = discord.ext.commands.Bot('!')


class MyCog(commands.Cog):
    def __init__(self, bot):
        self.chan = None
        self.bot = bot
        self.run_thread = True
        self.send_thread = Thread(target=lambda: self.packet_queue_thread())
        self.send_buffer = Buffer()

    async def transmit_bulk_packets(self, buffer):
        with buffer.buffer_lock:
            if not len(buffer.packets):
                return

            message = ''
            for packet in buffer.packets:
                message += packet + " "
            message = message[:-1]

            bio = io.BytesIO(message.encode())
            m_file = discord.File(bio)
            await self.chan.send(file=m_file, delete_after=1)
            buffer.clear()
            buffer.signal_free()

    def cog_unload(self):
        self.send_buffer.buffer_lock.release()
        self.run_thread = False
        self.send_thread.join()
        self.autoflusher.cancel()

    @tasks.loop(seconds=1)
    async def autoflusher(self):
        if self.send_buffer.totalSize:
            print(self.send_buffer.totalSize)
            print("autoflushing")
        else:
            print("not flushing, ", self.send_buffer.totalSize)
        await self.transmit_bulk_packets(self.send_buffer)

    def packet_queue_thread(self):
        if not self.chan:
            return
        print("sending has started")
        while self.run_thread:
            packet = tun.read(tun.mtu + 16)
            converted = ''.join([chr(i + int('0x80', 16)) for i in packet])
            self.send_buffer.queue_packet(converted)

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.author.bot:
            return
        if message.author == self.bot.user:
            return
        if not len(message.attachments):
            return

        data = io.BytesIO()

        await message.attachments[0].save(data)

        packets = data.getvalue().decode().split('\x20')
        for packet in packets:
            decoded_bytes = bytes([ord(i) - int('0x80', 16) for i in packet])
            tun.write(decoded_bytes)

    @commands.Cog.listener()
    async def on_ready(self):
        print('Ready!')
        print('Logged in as ---->', self.bot.user)
        print('ID:', self.bot.user.id)
        self.chan = discord.utils.get(bot.get_all_channels(), name="general")
        print("channel is: {}".format(self.chan))
        if not self.chan:
            bot.remove_cog('MyCog')

        self.autoflusher.start()
        self.send_thread.start()


bot.add_cog(MyCog(bot))
bot.run(TOKEN)
