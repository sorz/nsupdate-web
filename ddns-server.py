#!/usr/bin/env python3
import json
from base64 import b64decode
from argparse import ArgumentParser
from ipaddress import ip_address, IPv4Address
from subprocess import Popen, PIPE
from urllib.parse import urlparse, parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler


class HTTPRequestHandler(BaseHTTPRequestHandler):
    _host_ip_cache = {}

    def send(self, message, status=200):
        self.send_response(status)
        self.end_headers()
        self.wfile.write(message.encode())

    def send_unauthorized(self):
        self.send_response(401, 'Not Authorized')
        self.send_header('WWW-Authenticate', 
                         'Basic realm="%s"' % self.args.domain)
        self.end_headers()
        self.wfile.write(b'no auth')

    def do_GET(self):
        auth = self.headers.get('Authorization', '')
        if not auth.startswith('Basic '):
            self.send_unauthorized()
            return

        host, pwd = b64decode(auth[6:]).decode().split(':', 1)
        if host.endswith(self.args.domain):
            host = host[:-len(self.args.domain)]
        if self.server.host_auth.get(host) != pwd:
            self.send_unauthorized()
            return

        args = parse_qs(urlparse(self.path).query)
        if 'ip' in args:
            ip = [s.strip() for s in args['ip']]
        elif 'X-Real-IP' in self.headers:
            ip = [self.headers['X-Real-IP']]
        else:
            self.send('no address', 400)
            return

        try:
            ip = {ip_address(a) for a in ip}
        except AddressValueError as e:
            self.send('broken address\n%s' % e, 400)
            return

        if len(ip) > self.args.max_ip:
            self.send('too many addresses\nmax %s' % self.args.max_ip, 400)
            return

        if self._host_ip_cache.get(host) == ip:
            self.send('no-change', 200)
            return

        ok, msg = update_record('%s.%s' % (host, self.args.domain),
                                ip, self.args)
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
                        help='The address bind to, default to 127.0.0.1.')
    parser.add_argument('-p', '--listen-port',
                        default=8080, type=int, metavar='PORT')
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
    HTTPRequestHandler.args = args
    server = HTTPServer((args.listen_addr, args.listen_port),
                        HTTPRequestHandler)
    server.host_auth = json.load(open(args.host_list))
    server.serve_forever()


if __name__ == '__main__':
    main()

