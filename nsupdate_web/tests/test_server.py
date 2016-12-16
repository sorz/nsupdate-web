#!/usr/bin/env python3
from mock import patch

from .. import server


class TestServer(object):
    def setup(self):
        self.sysv_args = [
            '-d', 'domain.example.com',
        ]
        self.argparse_args = server._get_args(self.sysv_args)
        self.start_patchers()

    def start_patchers(self):
        self.patchers = list()
        self.patchers.extend([
            patch('nsupdate_web.server.HTTPServer.server_activate'),
            patch('nsupdate_web.server.HTTPServer.server_bind'),
            patch('nsupdate_web.server.HTTPServer.server_close'),
        ])
        for patcher in self.patchers:
            patcher.start()

    def teardown(self):
        self.stop_patchers()

    def stop_patchers(self):
        for patcher in self.patchers:
            patcher.stop()

    def test_default_args(self):
        args = self.argparse_args
        assert args.domain == 'domain.example.com'
        assert args.listen_addr == '127.0.0.1'
        assert args.listen_port == 8080
        assert args.socket_mode == '660'
        assert args.nsupdate == '/usr/bin/nsupdate'
        assert args.ttl == 300
        assert args.timeout == 3
        assert args.max_ip == 32

    def test_server_attrs(self):
        obj = server.get_server(self.argparse_args)
        assert obj.args is self.argparse_args
        assert hasattr(obj, 'host_auth')
