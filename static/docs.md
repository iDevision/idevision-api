Because i'm a lazy fuck, you get plaintext docs.

Tokens
========
tokens are required for certain endpoints, such as the private endpoints, cdn access (fetching images is available
to everyone at https://cdn.idevision.net, uploading images and viewing statistic endpoints requires a token), the OCR API, and so on. \
You can apply for a token to the OCR API by using the `idevision apply` command on the `BOB (dev)#0346` bot on discord. \
You will be denied if your name contains any sort of zalgo or otherwise not url-safe characters. This is done at my discresion. \
For any other endpoints, please message IAmTomahawkx#1000 on discord.


GET /api/public/rtfs
=======================

Ratelimit
----------
3 requests per 5 seconds (3/5s). \
Exceeding this api by double (6/5s) will result in an automatic api ban
(and disabling of your account, if you are using an API token). If you are using an API token, the rates above are doubled. \
Please follow the ratelimit-retry-after headers when you recieve a 429 response code.

Required Query parameters
---------------------------
- query : The actual query
- library : The module to find source for. One of twitchio, wavelink, or discord.py

Returns
--------
Response 200
```json
{
    "nodes": {"Node name": "URL to source"},
    "query_time": "1.0"
}
```

GET /api/public/rtfm
=======================

Ratelimit
----------
3 requests per 5 seconds (3/5s). \
Exceeding this api by double (6/5s) will result in an automatic api ban
(and disabling of your account, if you are using an API token). If you are using an API token, the rates above are doubled. \
Please follow the ratelimit-retry-after headers when you recieve a 429 response code.

Required Query parameters
---------------------------
- query : The actual query
- location : The location of the documentation. This can be any sphinx generated documentation. Ex. https://discordpy.readthedocs.io/en/latest
- show-labels : a boolean. When false, labels will not be returned in the results
- label-labels : a boolean. When true, labels will have `label:` prepended to them. Does nothing when show-labels is false

Returns
--------
Response 200
```json
{
    "nodes": {"Node name": "URL of the documentation"},
    "query_time": "1.0"
}
```