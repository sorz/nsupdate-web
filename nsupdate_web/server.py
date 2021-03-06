#!/usr/bin/env python3
import re
import sys
import json
from json import JSONDecodeError
from base64 import b64decode
from pathlib import Path
from argparse import ArgumentParser
from ipaddress import ip_address, IPv4Address, AddressValueError
from subprocess import Popen, PIPE, TimeoutExpired
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler
from socketserver import ThreadingTCPServer
try:
    from socketserver import ThreadingUnixStreamServer
except ImportError:
    ThreadingUnixStreamServer = None


class HTTPServer(ThreadingTCPServer):
    allow_reuse_address = 1


if ThreadingUnixStreamServer is not None:
    class UnixHTTPServer(ThreadingUnixStreamServer):
        pass
else:
    UnixHTTPServer = None


class HTTPRequestHandler(BaseHTTPRequestHandler):
    _host_ip_cache = {}

    def send(self, message, status=200):
        self.send_response(status)
        self.end_headers()
        self.wfile.write(message.encode())

    def send_unauthorized(self):
        self.send_response(401, 'Not Authorized')
        self.send_header('WWW-Authenticate',
                         'Basic realm="%s"' % self.server.args.domain)
        self.end_headers()
        self.wfile.write(b'no auth')

    def handle_one_request(self):
        if not self.client_address:
            self.client_address = ('unknown', 0)
        super().handle_one_request()

    def do_GET(self):
        args = parse_qs(urlparse(self.path).query)
        host = self.get_host(args)
        ips = self.get_ips(args)
        if not (host and ips):
            return

        if len(ips) > self.server.args.max_ip:
            msg = 'too many addresses\nmax %s' % self.server.args.max_ip
            self.send(msg, 400)
            return

        if self._host_ip_cache.get(host) == ips:
            self.send('no-change', 200)
            return

        self.do_update(host, ips)

    def get_host(self, args):
        if self.server.host_auth is not None:
            auth = self.headers.get('Authorization', '')
            if not auth.startswith('Basic '):
                self.send_unauthorized()
                return

            host, pwd = b64decode(auth[6:]).decode().split(':', 1)
            if host.endswith(self.server.args.domain):
                host = host[:-len(self.server.args.domain)]

            if self.server.host_auth.get(host) != pwd:
                self.send_unauthorized()
                return
        else:
            try:
                host = args['name'][0]
            except KeyError:
                self.send("Must specify 'name'", 400)
                return
        if self.server.args.allow_hosts and \
                not re.match(self.server.args.allow_hosts, host):
            self.send(
                "%s does not match the allow_hosts regex" % host,
                403
            )
            return
        return host

    def get_ips(self, args):
        if 'ip' in args:
            try:
                ips = [s.strip() for s in args['ip']]
            except KeyError:
                self.send("Must specify 'ip'", 400)
                return
        elif 'X-Real-IP' in self.headers:
            ips = [self.headers['X-Real-IP']]
            self.client_address = (ips[0], self.client_address[1])
        else:
            self.send('no address', 400)
            return

        try:
            ips = {ip_address(a) for a in ips}
        except (AddressValueError, ValueError) as e:
            self.send('broken address\n%s' % e, 400)
            return
        return ips

    def do_update(self, host, ips):
        ok, msg = update_record(
            host,
            ips,
            self.server.args
        )
        if ok:
            self._host_ip_cache[host] = ips
            self.send(msg, 200)
        else:
            self.send(msg, 500)


def update_record(host, addrs, args):
    popen_args = [args.nsupdate]
    if args.key_file:
        popen_args.extend(['-k', args.key_file])
    else:
        popen_args.append('-l')

    nsupdate = Popen(
        popen_args,
        universal_newlines=True,
        stdin=PIPE,
        stdout=PIPE,
        stderr=PIPE,
    )
    cmdline = list()
    if args.server:
        cmdline.append("server %s" % args.server)
    fqdn = "%s.%s" % (host, args.domain)
    cmdline.append("zone %s" % args.domain)
    cmdline.append("update delete %s" % fqdn)

    for addr in addrs:
        type = 'A' if isinstance(addr, IPv4Address) else 'AAAA'
        cmdline += ["update add {fqdn} {ttl} {type} {ip}"
                    .format(ttl=args.ttl, fqdn=fqdn, ip=addr, type=type)]
    cmdline += ["send", "quit"]
    try:
        outs, errs = nsupdate.communicate('\n'.join(cmdline), args.timeout)
    except TimeoutExpired:
        nsupdate.kill()
        return False, "timeout"

    if errs:
        return False, errs
    else:
        return True, "success"


def _get_args(args=None):
    parser = ArgumentParser(description='Web API for update DNS records.',
                            epilog='Author: Shell Chen <me@sorz.org>.')
    parser.add_argument('-l', '--listen-addr',
                        default='127.0.0.1', metavar='ADDRESS',
                        help='The address bind to, default to 127.0.0.1. '
                             'Set a path to listen on Unix domain socket.')
    parser.add_argument('-p', '--listen-port',
                        default=8080, type=int, metavar='PORT')
    parser.add_argument('-s', '--server',
                        help='The remote nameserver')
    parser.add_argument('-m', '--socket-mode',
                        default='660', metavar='FILE-MODE',
                        help='File mode (chmod) of Unix domain socket, '
                             'default to 660. Ignored on TCP mode.')
    parser.add_argument('-k', '--host-list',
                        metavar='HOST-FILE',
                        help='The json file contains hostname-key pairs.')
    parser.add_argument('-a', '--allow-hosts',
                        help='Only accept updates for hosts matching this '
                        'regular expression')
    parser.add_argument('-K', '--key-file',
                        help='The keyfile to use with nsupdate')
    parser.add_argument('-d', '--domain',
                        metavar='DOMAIN_SUFFIX',
                        required=True,
                        help='Example: dyn.example.com')
    parser.add_argument('--nsupdate',
                        default='/usr/bin/nsupdate', metavar='NSUPDATE-PATH')
    parser.add_argument('--ttl',
                        default='300', type=int, metavar='SECONDS')
    parser.add_argument('--max-ip',
                        default='32', type=int, metavar='MAX-IP',
                        help='Max allowed number of IPs on each name.')
    parser.add_argument('--timeout',
                        default='3', type=int, metavar='SECONDS',
                        help='Max waitting time for nsupdate.')

    return parser.parse_args(args)


class InitFailed(object):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return "%s" % self.msg


def get_server(args, host_auth=None):
    if args.listen_addr.startswith('/'):
        # A unix socket address
        sock = Path(args.listen_addr)
        if sock.is_socket():
            sock.unlink()
        if UnixHTTPServer is None:
            raise InitFailed(
                'Unix domain socket is unsupported on this platform.'
            )
        server = UnixHTTPServer(str(sock), HTTPRequestHandler)
        sock.chmod(int(args.socket_mode, 8))
    else:
        server = HTTPServer((args.listen_addr, args.listen_port),
                            HTTPRequestHandler)

    server.args = args
    server.host_auth = host_auth
    return server


def main():
    args = _get_args(sys.argv[1:])

    host_auth = None
    if args.host_list is not None:
        try:
            with open(args.host_list) as f:
                host_auth = json.load(f)
        except (FileNotFoundError, JSONDecodeError, PermissionError) as e:
            print('Cannot read host list file %s.' % args.host_list)
            print(e)
            sys.exit(2)

    try:
        server = get_server(args, host_auth)
    except InitFailed as e:
        print(str(e))
        sys.exit(1)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('Exit on ^C.')
