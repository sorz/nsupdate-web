#!/usr/bin/env python3
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

        args = parse_qs(urlparse(self.path).query)
        if 'ip' in args:
            ip = [s.strip() for s in args['ip']]
        elif 'X-Real-IP' in self.headers:
            ip = [self.headers['X-Real-IP']]
            self.client_address = (ip[0], self.client_address[1])
        else:
            self.send('no address', 400)
            return

        try:
            ip = {ip_address(a) for a in ip}
        except AddressValueError as e:
            self.send('broken address\n%s' % e, 400)
            return

        if len(ip) > self.server.args.max_ip:
            msg = 'too many addresses\nmax %s' % self.server.args.max_ip
            self.send(msg, 400)
            return

        if self._host_ip_cache.get(host) == ip:
            self.send('no-change', 200)
            return

        ok, msg = update_record('%s.%s' % (host, self.server.args.domain),
                                ip, self.server.args)
        if ok:
            self._host_ip_cache[host] = ip
            self.send(msg, 200)
        else:
            self.send(msg, 500)


def update_record(domain, addrs, args):
    nsupdate = Popen([args.nsupdate, '-l'], universal_newlines=True,
                     stdin=PIPE, stdout=PIPE, stderr=PIPE)
    cmdline = ["del %s" % domain]
    for addr in addrs:
        type = 'A' if isinstance(addr, IPv4Address) else 'AAAA'
        cmdline += ["add {domain} {ttl} {type} {ip}"
                    .format(ttl=args.ttl, domain=domain, ip=addr, type=type)]
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


def _get_args():
    parser = ArgumentParser(description='Web API for update DNS records.',
                            epilog='Author: Shell Chen <me@sorz.org>.')
    parser.add_argument('-l', '--listen-addr',
                        default='127.0.0.1', metavar='ADDRESS',
                        help='The address bind to, default to 127.0.0.1. '
                             'Set a path to listen on Unix domain socket.')
    parser.add_argument('-p', '--listen-port',
                        default=8080, type=int, metavar='PORT')
    parser.add_argument('-m', '--socket-mode',
                        default='660', metavar='FILE-MODE',
                        help='File mode (chmod) of Unix domain socket, '
                             'default to 660. Ignored on TCP mode.')
    parser.add_argument('-k', '--host-list',
                        metavar='HOST-FILE',
                        help='The json file contains hostname-key pairs.')
    parser.add_argument('-d', '--domain',
                        metavar='DOMAIN_SUFFIX',
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

    return parser.parse_args()


def main():
    args = _get_args()
    if args.host_list is None:
        print('Please specify --host-list.')
        sys.exit(1)
    if args.domain is None:
        print('Please specify --domain.')
        sys.exit(1)
    try:
        with open(args.host_list) as f:
            host_auth = json.load(f)
    except (FileNotFoundError, JSONDecodeError, PermissionError) as e:
        print('Cannot read host list file %s.' % args.host_list)
        print(e)
        sys.exit(2)

    if args.listen_addr.startswith('/'):
        # A unix socket address
        sock = Path(args.listen_addr)
        if sock.is_socket():
            sock.unlink()
        if UnixHTTPServer is None:
            print('Unix domain socket is unsupported on this platform.')
            sys.exit(1)
        server = UnixHTTPServer(str(sock), HTTPRequestHandler)
        sock.chmod(int(args.socket_mode, 8))
    else:
        server = HTTPServer((args.listen_addr, args.listen_port),
                            HTTPRequestHandler)

    server.args = args
    server.host_auth = host_auth
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('Exit on ^C.')

if __name__ == '__main__':
    main()

