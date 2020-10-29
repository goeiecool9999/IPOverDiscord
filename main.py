import signal
from asyncio import Event
from concurrent.futures.thread import ThreadPoolExecutor

from pytun import TunTapDevice
import discord
from discord.ext import tasks, commands

import os

import logging

from modem import Encoder, Decoder

logging.basicConfig(level=logging.INFO)

tun = TunTapDevice(name='discip')
tun.addr = os.environ['SRC_IP']
tun.dstaddr = os.environ['DST_IP']
tun.netmask = '255.255.255.0'
tun.mtu = 1990
tun.persist(True)
tun.up()


def terminate():
    tun.down()


signal.signal(signal.SIGINT, terminate)

threadpool = ThreadPoolExecutor(2)

import ctypes.util
discord.opus.load_opus(ctypes.util.find_library('opus'))
discord.opus.is_loaded()

TOKEN = os.environ["DISCORD_TOKEN"]

bot = discord.ext.commands.Bot('!')


class MyCog(commands.Cog):
    def __init__(self, bot):
        self.chan = None
        self.bot = bot
        self.encoder = Encoder()
        self.encoder_available_event = Event()
        self.encoder_available_event.set()
        self.decoder = Decoder(lambda packet: self.handle_packet(packet))
        self.vcclient = None

    def cog_unload(self):
        self.printer.cancel()

    def handle_packet(self,packet):
        tun.write(packet)

    async def printer(self):
        print("sending has started")
        while True:
            packet = await bot.loop.run_in_executor(threadpool, (lambda: tun.read(tun.mtu + 16)))
            packet = "this is a test".encode('ascii')
            await self.encoder_available_event.wait()
            self.encoder_available_event.clear()
            self.encoder.set_bytes_to_play(packet)
            self.vcclient.play(self.encoder, after=lambda x: self.encoder_available_event.set())

    @commands.Cog.listener()
    async def on_ready(self):
        print('Ready!')
        print('Logged in as ---->', self.bot.user)
        print('ID:', self.bot.user.id)
        self.chan = discord.utils.get(bot.get_all_channels(), name="General")
        print("channel is: {}".format(self.chan))
        if not self.chan:
            bot.remove_cog('MyCog')

        self.vcclient = await self.chan.connect()
        if not self.vcclient:
            bot.remove_cog('MyCog')

        self.vcclient.listen(self.decoder)
        self.bot.loop.create_task(self.printer())


bot.add_cog(MyCog(bot))
bot.run(TOKEN)
