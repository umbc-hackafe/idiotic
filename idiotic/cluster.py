from idiotic import config
from idiotic import block
import pysyncobj
import logging
import asyncio
import aiohttp
from aiohttp import web
import json

log = logging.Logger('idiotic.cluster')


class UnassignableBlock(Exception):
    pass


class Cluster(pysyncobj.SyncObj):
    def __init__(self, configuration: config.Config):
        super(Cluster, self).__init__(
            '{}:{}'.format(configuration.hostname, configuration.cluster['port']),
            configuration.cluster['connect']
        )
        self.config = configuration
        self.block_owners = {}
        self.block_lock = asyncio.locks.Lock()
        self.resources = {}
        self.jobs = []

    async def find_destinations(self, event):
        return self.config.nodes.keys()

    def get_rpc_url(self, node):
        return "http://{}:{}/rpc".format(node, self.config.connect["port"])

    @pysyncobj.replicated
    async def assign_block(self, block: block.Block):

        with await self.block_lock:
            self.block_owners[block] = None
            nodes = await block.precheck_nodes(self.config)

            for node in nodes:
                self.block_owners[block] = node
                # Later: somehow tell the other node they have a new block
                return

            raise UnassignableBlock(block)


class Node:
    def __init__(self, name: str, cluster: Cluster, config: config.Config):
        self.name = name
        self.cluster = cluster
        self.config = config

        self.events_out = asyncio.Queue()
        self.events_in = asyncio.Queue()

    def dispatch(self, event):
        self.events_out.put_nowait(event)

    def event_received(self, event):
        log.debug("Event received: {}", event)
        # don't know what to do here

    async def run(self):
        await asyncio.gather(self.run_dispatch(), self.run_messaging())

    async def run_dispatch(self):
        while True:
            event = await self.events_out.get()

            for dest in self.cluster.find_destinations(event):
                url = self.cluster.get_rpc_url(dest)
                # Screw you aiohttp, I do what I want!
                await aiohttp.request('POST', url, data=json.dumps(event))

    async def rpc_endpoint(self, request):
        self.events_in.put_nowait(await request.json())
        return web.Response(text="Success")

    async def run_messaging(self):
        app = web.Application()
        app.router.add_route('POST', '/rpc', self.rpc_endpoint, name='rpc')
        handler = app.make_handler()
        await asyncio.get_event_loop().create_server(handler, self.config.cluster['listen'], self.config.cluster['port'])
