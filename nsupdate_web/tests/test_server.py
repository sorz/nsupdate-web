#!/usr/bin/env python3
import requests
import threading

from mock import patch

from .. import server


class TestServer(object):
    def setup(self):
        self.sysv_args = [
            '-d', 'domain.example.com',
        ]
        self.argparse_args = server._get_args(self.sysv_args)
        self.base_url = 'http://localhost:8080'
        self.start_patchers()

    def start_patchers(self):
        self.patchers = list()
        self.patches = dict(
            update_record=dict(
                target='nsupdate_web.server.update_record'
            ),
        )
        for name in self.patches.keys():
            patcher = patch(self.patches[name]['target'])
            self.patches[name].update(
                patcher=patcher,
                mock=patcher.start(),
            )

    def teardown(self):
        self.stop_patchers()

    def stop_patchers(self):
        for obj in self.patches.values():
            obj['patcher'].stop()

    def start_serving(self):
        self.server_thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.server_thread.start()

    def stop_serving(self):
        self.server.shutdown()
        self.server.server_close()

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

    def test_basic_request(self):
        m_update_record = self.patches['update_record']['mock']
        m_update_record.return_value = (True, 'success')
        self.server = server.get_server(self.argparse_args)
        self.start_serving()
        resp = requests.get(
            self.base_url + '/update?name=foo&ip=10.1.1.1'
        )
        assert resp.ok
        self.stop_serving()

    def test_no_name(self):
        self.server = server.get_server(self.argparse_args)
        self.start_serving()
        resp = requests.get(
            self.base_url + '/update?ip=10.1.1.1'
        )
        assert not resp.ok
        assert resp.text == "Must specify 'name'"
        self.stop_serving()

    def test_no_ip(self):
        self.server = server.get_server(self.argparse_args)
        self.start_serving()
        resp = requests.get(
            self.base_url + '/update?name=foo'
        )
        assert not resp.ok
        assert resp.text == "no address"
        self.stop_serving()

    def test_broken_ip(self):
        self.server = server.get_server(self.argparse_args)
        self.start_serving()
        resp = requests.get(
            self.base_url + '/update?name=foo&ip=not_an_ip'
        )
        assert not resp.ok
        self.stop_serving()
