import ipaddress
import os

from starlette.responses import PlainTextResponse


class InternalNetwork:
    def __init__(self, app):
        self.app = app
        ranges = os.environ.get('ACOUSTIC_ALLOWED_NETWORKS', '127.0.0.0/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16')
        self.networks = [ipaddress.ip_network(item.strip()) for item in ranges.split(',')]

    async def __call__(self, scope, receive, send):
        if scope['type'] in ('http', 'websocket'):
            try:
                address = ipaddress.ip_address(scope['client'][0])
                allowed = any(address in network for network in self.networks)
            except (TypeError, ValueError):
                allowed = False
            if not allowed:
                if scope['type'] == 'websocket':
                    await send({'type':'websocket.close','code':4403})
                else:
                    await PlainTextResponse('不允許此網路存取',403)(scope,receive,send)
                return
        await self.app(scope,receive,send)
