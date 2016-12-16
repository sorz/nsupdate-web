#!/usr/bin/env python3
from .. import server


class TestServer(object):
    def setup(self):
        self.args = [
            '-d', 'domain.example.com',
        ]

    def test_default_args(self):
        args = server._get_args(self.args)
        assert args.domain == 'domain.example.com'
        assert args.listen_addr == '127.0.0.1'
        assert args.listen_port == 8080
        assert args.socket_mode == '660'
        assert args.nsupdate == '/usr/bin/nsupdate'
        assert args.ttl == 300
        assert args.timeout == 3
        assert args.max_ip == 32
