# nsupdate-web

Simple DDNS (dynamic DNS) web API service with _nsupdate (8)_.

It's a single-file Python 3 script accepting HTTP requests and changing DNS records on BIND server with _nsupdate (8)_.

## Features

 * Update IP addresses with a simple `curl` or `wget` command
 * Support multiple _A_ and/or _AAAA_ records for each domain name
 * Pure Python, standard library only

## Usages

### Start script
Print usages:

```
$ ./ddns-server.py -h
usage: ddns-server.py [-h] [-l ADDRESS] [-p PORT] [-m FILE-MODE]
                      [-k HOST-FILE] [-d DOMAIN_SUFFIX]
                      [--nsupdate NSUPDATE-PATH] [--ttl SECONDS]
                      [--max-ip MAX-IP] [--timeout SECONDS]

Web API for update DNS records.

optional arguments:
  -h, --help            show this help message and exit
  -l ADDRESS, --listen-addr ADDRESS
                        The address bind to, default to 127.0.0.1. Set a path
                        to listen on Unix domain socket.
  -p PORT, --listen-port PORT
  -m FILE-MODE, --socket-mode FILE-MODE
                        File mode (chmod) of Unix domain socket, default to
                        660. Ignored on TCP mode.
  -k HOST-FILE, --host-list HOST-FILE
                        The json file contains hostname-key pairs.
  -d DOMAIN_SUFFIX, --domain DOMAIN_SUFFIX
                        Example: dyn.example.com
  --nsupdate NSUPDATE-PATH
  --ttl SECONDS
  --max-ip MAX-IP       Max allowed number of IPs on each name.
  --timeout SECONDS     Max waitting time for nsupdate.

```

Serving _dyn.example.com_ on _127.0.0.1:8080_:
```
$ ./ddns-server.py -l 127.0.0.1 -p 8080 -k hosts.json -d dyn.example.com
```
_hosts.json_ is a JSON file which contains all hostname-password pairs:
```
{
  'test': 'pwd123',
  'elder': 'mogic'
}
```

### Update addresses
See examples below.
```
$ curl https://test:pwd123@dyn.example.com/update
> success
$ dig +short test.dyn.example.com
> 198.51.100.5

$ curl https://test:pwd123@dyn.example.com/update?ip=192.0.2.8
> success
$ dig +short test.dyn.example.com
> 192.0.2.8

$ curl https://elder:mogic@dyn.example.com/update?ip=2001:DB8::1968:08:17&ip=192.0.2.8&ip=198.51.100.5
> success
$ dig +short elder.dyn.example.com aaaa
> 2001:db8::1968:8:17
$ dig +short elder.dyn.example.com a
> 192.0.2.8
  198.51.100.5

```


## Install

### Prerequisites

* Python 3 (for running this script)
* BIND 9 (for serving zones)
* Nginx (for rewriting URLs and HTTPS support)
* `nsupdate` (possibly included in BIND)

Note that this script only communicate with BIND via `nsupdate`, so you have to configure your BIND server allowing updating records with `nsupdate` tool. 

### Run as a service

Add this systemd service file as `/etc/systemd/system/ddns-server.service`:

```
[Unit]
Description=DDNS HTTP update service.

[Service]
Type=simple
User=named
Group=named
ExecStart=/usr/bin/python3 /path/to/ddns-server.py -k /path/to/hosts.json -p 8080 -d dyn.example.com
ExecStopPost=/usr/bin/rndc sync -clean dyn.example.com

[Install]
WantedBy=multi-user.target

```
Enable and start:
```
$ sudo systemctl enable ddns-server
$ sudo systemctl start ddns-server
```

### Nginx configuration
Here is a example:

```
server {
	listen 443 ssl http2;
    
    location / {
    	root /srv/http/ddns;
        index index.html;
        # Provide some helpful explanations here.
    }
    
    location = /update {
    	include proxy_params;
        proxy_pass http://localhost:8080;
    }
    
    # To be compatible with HE.net's DDNS clients/scripts. 
    rewrite ^/nic/update$ /update last;
}
```

