from . import base
import logging
import socket
import string
import struct
import queue
import json

PACKET_HEAD = b"ID10T"
ID_EVENT = 1
ID_DISCOVERY = 2

EVENT = 1
DISCOVERY = 2

FORMAT = {
    EVENT: "{}s",
    DISCOVERY: "H{}s",
}

HEADER_FORMAT = "!5sBI"
EVENT_FORMAT = "s"
DISCOVERY_FORMAT = "Hs"
HEADER_LEN = struct.calcsize(HEADER_FORMAT)

log = logging.getLogger("idiotic.distrib.udp")

class UDPItem(base.RemoteItem):
    pass

class UDPModule(base.RemoteModule):
    pass

class UDPNeighbor(base.Neighbor):
    def __init__(self, name, host, port):
        self.name = name
        self.host = host
        self.port = port
        self.modules = []
        self.items = [] 

class UDPTransportMethod(base.TransportMethod):
    NEIGHBOR_CLASS = UDPNeighbor
    MODULE_CLASS = UDPModule
    ITEM_CLASS = UDPItem

    def __init__(self, hostname, config):
        self.hostname = hostname

        config = config or {}

        self.listen_port = config.get("port", 28300)
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.listener.settimeout(5)
        self.listener.bind(('', self.listen_port))

        self.sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sender.bind(('', 0))
        self.sender.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        self.incoming = queue.Queue()
        self.neighbor_dict = {}

        self.running = False

    def _encode_packet(self, kind, *data):
        strlens = [len(s) for s in data if type(s) is str]
        msg_len = struct.calcsize('!' + FORMAT[kind].format(*strlens))

        return struct.pack(HEADER_FORMAT + FORMAT[kind].format(*strlens),
                           PACKET_HEAD, kind, msg_len,
                           *[s.encode('UTF-8') if type(s) is str else s for s in data])

    def _decode_packet(self, data):
        head, kind, data_len = struct.unpack_from(HEADER_FORMAT, data)

        if head != PACKET_HEAD:
            raise ValueError("Invalid packet header '{}'".format(head))

        if kind == EVENT:
            tup = struct.unpack_from(FORMAT[EVENT].format(data_len), data, HEADER_LEN)
        elif kind == DISCOVERY:
            port, host = struct.unpack_from(FORMAT[DISCOVERY].format(
                data_len - struct.calcsize(FORMAT[DISCOVERY][:1])), data, HEADER_LEN)
            tup = port, host.decode('UTF-8')
        return kind, tup

    def _send_discovery(self, target='<broadcast>', port=None):
        if port is None:
            port = self.listen_port
        self.sender.sendto(self._encode_packet(DISCOVERY,
                                               self.listen_port, self.hostname),
                           (target, port))

    def connect(self):
        self._send_discovery()

    def run(self):
        self.running = True
        while self.running:
            try:
                data, addr = self.listener.recvfrom(2048)
                log.debug("Received '{}' from {}".format(data, addr))
                try:
                    kind, tup = self._decode_packet(data)
                except ValueError:
                    log.error("Received invalid packet from {}: {}".format(addr, data))
                if kind == DISCOVERY:
                    log.debug("Received discovery packet")

                    port, host = tup

                    if host in self.neighbor_dict:
                        log.debug("Updating existing neighbor {}".format(host))
                        self.neighbor_dict[host].name = host
                        self.neighbor_dict[host].host = addr
                        self.neighbor_dict[host].port = port
                    else:
                        log.info("Found new neighbor {} at {}".format(host, addr))
                        self.neighbor_dict[host] = UDPNeighbor(host, addr, port)
                elif kind == ID_EVENT:
                    log.debug("Received event packet")

                else:
                    log.debug("Bad header: {}".format(header))
            except socket.timeout:
                continue

    def stop(self):
        self.running = False

    def disconnect(self):
        pass

    def send(self, event, targets=True):
        if targets is True:
            self.sender.sendto(struct.pack(HEADER_FORMAT + EVENT_FORMAT,
                                           PACKET_HEAD, ID_EVENT,
                                           event))
        else:
            log.error("Sending to individual targets is not yet supported.")

    def neighbors(self):
        return list(self.neighbor_dict.values())

METHOD = UDPTransportMethod