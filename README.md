# nsupdate-web

Simple DDNS (dynamic DNS) web API service with _nsupdate (8)_.

It's a small Python 3 library and companion script accepting HTTP requests
and changing DNS records on BIND server with _nsupdate (8)_.

## Features

 * Update IP addresses with a simple `curl` or `wget` command
 * Support multiple _A_ and/or _AAAA_ records for each domain name
 * Pure Python, standard library only (aside from tests)

## Usage
See `./ddns-server.py --help`

### Start script
Serving _dyn.example.com_ on _127.0.0.1:8080_, updating `named` on _localhost_ using a host file:
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

Serving _dyn.example.com_ on _127.0.0.1:8080_, updating `named` on _ns1.example.com_ using a key file:
```
./ddns-server.py -d dyn.example.com -K ./Kdyn.example.com.+123+12345.key -s ns1.example.com
```

### Update addresses
When using a host file:
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

Without a host file, if authentication is not needed:
```
$ curl "http://dyn.example.com:8080/update?name=test&ip=192.0.2.8"
> success
$ dig +short test.dyn.example.com
> 192.0.2.8
```

## Install
From a `git` clone:
```
$ python setup.py install
```
After installation, `ddns-server` will be in `$PATH`

### Prerequisites

* Python 3 (for running this script)
* BIND 9 (for serving zones)
* Nginx (for rewriting URLs and HTTPS support)
* `nsupdate` (possibly included in BIND)

Note that this script only communicate with BIND via `nsupdate`, so you 
 have to configure your BIND server allowing updating records with the
 `nsupdate` tool.

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
