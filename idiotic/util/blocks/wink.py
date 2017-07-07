import requests
from idiotic import block
from idiotic import resource
from idiotic import node
import asyncio
import aiohttp


class WinkDeviceNotFound(Exception):
    pass


class Device(block.Block):
    def __init__(self, name, **config):
        self.name = name
        self.config = {"base_url": "https://winkapi.quirky.com",
                       "client_id": "quirky_wink_android_app",
                       "client_secret": "e749124ad386a5a35c0ab554a4f2c045",
                       "username": "",
                       "password": "",
                       "wink_name": "",
                       "wink_label": "",
                       "wink_id": "",
                      }
        self.config.update(config)

        self.auth = None
        self.wink = None
        self.device = None

        self.inputs = {}
        self.resources = [resource.HTTPResource(self.config['base_url'])]

    async def run(self, *_, **__):
        import wink

        self.auth = wink.auth(**self.config)
        self.wink = wink.Wink(self.auth, save_auth=False)
        self.device = self.find()

        if not self.device:
            raise WinkDeviceNotFound("None of the provided criteria matched any devices in your Wink account")

        await super().run()

    def find(self):
        devices = self.wink.device_list()
        for field in ['id', 'label', 'name']:
            for dev in devices:
                value = dev.data.get(field)
                if value and value == self.config["wink_" + field]:
                    return dev


class Toggle(Device):
    def __init__(self, name, **config):
        super().__init__(name, **config)
        self.power_state = None

    async def power(self, value):
        self.power_state = value

        await asyncio.get_event_loop().run_in_executor(None, self.device.turn_on if value else self.device.turn_off)


class Dimmer(Toggle):
    def __init__(self, name, **config):
        super().__init__(name, **config)
        self.brightness = None

    async def brightness(self, value):
        self.brightness = value

        await asyncio.get_event_loop().run_in_executor(None, self.device.set_brightness, value)
