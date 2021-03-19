Idevision API Version 3.0

# Tokens
tokens are required for certain endpoints, such as the private endpoints, cdn access (fetching images is available
to everyone at https://cdn.idevision.net, uploading images and viewing statistic endpoints requires a token), the OCR API, and so on. 
You can apply for a token to the OCR API by using the `idevision apply` command on the `BOB (dev)#0346` bot on discord.
You will be denied if your name contains any sort of zalgo or otherwise not url-safe characters. This is done at my discretion.
For any other endpoints, please message IAmTomahawkx#1000 on discord.

___

# Public Endpoints

## GET /api/public/rtfs
This Endpoint indexes a python module, and returns links to the source on github for functions and classes closest to the query provided.
If you have a module you wish to be included in the rtfs index, please contact me on discord: IAmTomahawkx#1000

### Ratelimit
3 requests per 5 seconds (3/5s).
Exceeding this api by double (6/5s) will result in an automatic api ban (and disabling of your account, if you are using an API token). If you are using an API token, the rates above are doubled.
Please follow the ratelimit-retry-after headers when you receive a 429 response code.

### Required Query parameters
- query : The actual query
- library : The module to find source for. One of twitchio, wavelink, or discord.py

### Returns
Response 200
```json
{
    "nodes": {"Node name": "URL to source"},
    "query_time": "1.0"
}
```

## GET /api/public/rtfm
This endpoint indexes sphinx repositories and returns documentation locations for items closest to the query provided. (rustdoc support may be coming soon)

### Ratelimit
3 requests per 5 seconds (3/5s).
Exceeding this api by double (6/5s) will result in an automatic api ban (and disabling of your account, if you are using an API token). If you are using an API token, the rates above are doubled.
Please follow the ratelimit-retry-after headers when you receive a 429 response code.

### Required Query parameters
- query : The actual query
- location : The location of the documentation. This can be any sphinx generated documentation. Ex. https://discordpy.readthedocs.io/en/latest
- show-labels : a boolean. When false, labels will not be returned in the results
- label-labels : a boolean. When true, labels will have `label:` prepended to them. Does nothing when show-labels is false

### Returns
Response 200
```json
{
    "nodes": {"Node name": "URL of the documentation"},
    "query_time": "1.0"
}
```

## GET /api/public/ocr

* Requires an idevision API token

This endpoint takes a multipart file, and returns the contents of the image as text.
> this endpoint may take longer to respond, depending on the amount of traffic flowing through the endpoint.
> Only two images are processed at a time (globally).

### Ratelimit
2 requests per 10 seconds (2/10s).
Exceeding this api by double (4/10s) will result in an automatic api ban (and disabling of your account, if you are using an API token). If you are using an API token, the rates above are doubled.
Please follow the ratelimit-retry-after headers when you receive a 429 response code.

### Required Query parameters
None

### Returns
Response 200
```json
{
    "data": "Content here"
}
```

## POST /api/homepage
* Requires an idevision API token

This endpoint allows you to set up a customized homepage, viewable at https://idevision.net/homepage?user=<your-username>
Anyone may access this, so don't put private links that do not require authorization.

### Ratelimit
5 requests per 30 seconds (5/30s).
Exceeding this api by double (10/30s) will result in an automatic api ban (and disabling of your account, if you are using an API token). If you are using an API token, the rates above are doubled.
Please follow the ratelimit-retry-after headers when you receive a 429 response code.

### Example Payload
```json
{
    "link1": "https://duckduckgo.com",
    "link1_name": "DuckDuckGo",
    "link2": "https://github.com",
    "link2_name": "GitHub",
    "link3": "https://discord.com",
    "link3_name": "Discord",
    "link4": "https://idevision.net",
    "link4_name": "IDevision"
}
```

### Returns
Response 204
[empty]

___

# Routes & permissions
### Users
- GET /api/internal/users
  - users
- POST /api/internal/users/apply
  - users.manage
- POST /api/internal/users/accept
  - users.manage
- POST /api/internal/users/deny
  - users.manage
- POST /api/internal/users/token
  - users.manage - may reset anyone's token
  - authorized request - may reset their own token
- POST /api/internal/users/manage
  - users.manage
- POST /api/internal/users/deauth
  - users.manage
- POST /api/internal/users/auth
  - users.manage
- GET /api/internal/bans
  - users.bans
- POST /api/internal/bans
  - users.bans

### Public
- POST /api/public/ocr
  - public.ocr
- POST /api/homepage
  - (any authorization)
- GET /api/public/rtfm
  - (public)
- GET /api/public/rtfs
  - (public)
- GET /
  - (public)

### CDN
- GET /api/cdn
  - (public)
- POST /api/cdn
  - cdn
  - users.manage - may specify node to upload to
- GET /api/cdn/{node}/{image}
  - cdn
- DELETE /api/cdn/{node}/{image}
  - cdn - May delete an image they have uploaded
  - cdn.manage - May delete any image
- POST /api/cdn/purge
  - cdn.manage
- GET /api/cdn/list
  - cdn.manage
- GET /api/cdn/list/{user}
  - cdn.manage - May list any user
  - cdn - May list themselves
- GET /api/cdn/user
  - cdn.manage - May get any user
  - cdn - May get themselves

___

# Legal
I reserve the right to deny access of anyone to this service at any time, for any reason.
I reserve the right to remove images from the cdn at any time, for any reason.
By using this service, you agree that I may collect usage info.
Any images uploaded to this cdn are public.
These policies may change at any time, without warning.

IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, 
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SERVICE OR THE 
USE OR OTHER DEALINGS IN THE SERVICE.