Idevision API Version 3.3

#####3.3
- Added /api/public/xkcd
- Added /api/public/xkcd/tags
- Added cache status to rtfm response
- Added module index when no query parameters passed to rtfs

#####3.2
- **Version 3.2 contains breaking changes to the /api/public/ocr endpoint**

# Tokens
tokens are required for certain endpoints, such as the private endpoints, cdn access (fetching images is available
to everyone at https://cdn.idevision.net, uploading images and viewing statistic endpoints requires a token), the OCR API, and so on. 
You can apply for a token to the OCR API by using the `idevision apply` command on the `BOB (dev)#0346` bot on discord.
You will be denied if your name contains any sort of zalgo or otherwise not url-safe characters. This is done at my discretion.
For any other endpoints, please message IAmTomahawkx#1000 on discord.

---
# Support
Support is available via [discord](https://discord.gg/xYSRTrjUun "Idevision support server")

___

# Public Endpoints

## GET /api/public/rtfs
This Endpoint indexes a python module, and returns links to the source on github for functions and classes closest to the query provided.
If you have a module you wish to be included in the rtfs index, please contact me on discord: IAmTomahawkx#1000

### Ratelimit
3 requests per 5 seconds (3/5s).
Exceeding this api by double (6/5s) will result in an automatic api ban (and disabling of your account, if you are using an API token). If you are using an API token, the rates above are doubled.
Please follow the ratelimit-retry-after headers when you receive a 429 response code.

### Available Libraries (in no particular order)
- twitchio
- wavelink
- discord.py
- aiohttp

### Required Query parameters
(These are not strictly required, but are required to preform a search)
- query : The actual query
- library : The library to find source for

### Optional Query parameters
- format : the format to return the data as. Can be one of `links` (returns links to the github source) or `source` (returns the source itself). Defaults to `links`

### Returns
Response 200 (when query and library parameters passed)
```json
{
    "nodes": {"Node name": "URL to source"},
    "query_time": "1.0"
}
```
Response 200 (when no query parameters passed)
```json
{
  "libraries": {
    "discord.py": "1.7.1",
    "twitchio": "1.2.2",
    "wavelink": "0.9.9",
    "aiohttp": "3.7.4.post0"
  }, 
  "notice": "The 'query' and 'lib' parameters must be provided to preform a search"
}
```
___

## GET /api/public/rtfm
This endpoint indexes sphinx repositories and returns documentation locations for items closest to the query provided. (rustdoc support may be coming soon)

### Ratelimit
3 requests per 5 seconds (3/5s).
Exceeding this api by double (6/5s) will result in an automatic api ban (and disabling of your account, if you are using an API token). If you are using an API token, the rates above are doubled.
Please follow the ratelimit-retry-after headers when you receive a 429 response code.

### Required Query parameters
- query : The actual query
- location : The location of the documentation. This can be any sphinx generated documentation. Ex. https://discordpy.readthedocs.io/en/latest

### Optional Query parameters
- show-labels : a boolean. When false, labels will not be returned in the results. Defaults to `true`
- label-labels : a boolean. When true, labels will have `label:` prepended to them. Does nothing when show-labels is false. Defaults to `false`

### Returns
Response 200
```json
{
    "nodes": {"Node name": "URL of the documentation"},
    "query_time": "1.0",
    "_cache_indexed": "2021-04-07T05:54:47.939360",
    "_cache_expires": "2021-04-07T05:54:47.939360"
}
```
___

## GET /api/public/ocr

* Requires an idevision API token with the `public.ocr` permission group

This endpoint takes an image as a bytes stream, and returns the contents of the image as text.
> this endpoint may take longer to respond, depending on the amount of traffic flowing through the endpoint.
> Only two images are processed at a time (globally).

Note that this model currently does not work well with dark backgrounds. Inverting dark backgrounds before uploading will lead to much better results

### Ratelimit
2 requests per 10 seconds (2/10s).
Exceeding this api by double (4/10s) will result in an automatic api ban (and disabling of your account, if you are using an API token). If you are using an API token, the rates above are doubled.
Please follow the ratelimit-retry-after headers when you receive a 429 response code.

### Required Query parameters
- filetype : the file extension of the uploaded file

### Returns
Response 200
```json
{
    "data": "Content here"
}
```
___

## GET /api/public/xkcd
Allows you to search for xkcd webcomics by name.

### Ratelimit
10 requests per 10 seconds (10/10s).
Exceeding this api by double (20/10s) will result in an automatic api ban (and disabling of your account, if you are using an API token). If you are using an API token, the rates above are doubled.
Please follow the ratelimit-retry-after headers when you receive a 429 response code.

### Required Query parameters
- query : the query to search for

### Returns
Response 200
```json
{
  "nodes": [
    {
      "num": 123,
      "posted": "2007-06-06T00:00:00",
      "safe_title": "A Title",
      "title": "A Title",
      "alt": "Witty Comment",
      "transcript": "Sometimes has a transcript of the comic",
      "news": "Sometimes has site news",
      "image_url": "https://imgs.xkcd.com/comics/...",
      "url": "https://xkcd.com/123"
    }
  ],
  "query_time": 0.011
}
```

## PUT /api/public/xkcd/tags

* Requires an idevision API token

Allows you to add a tag to a comic number, which will change search results for the word.
A tag may only exist once across all comics.

### Ratelimit
2 requests per 10 seconds (2/10s).
Exceeding this api by double (4/10s) will result in an automatic api ban.
Please follow the ratelimit-retry-after headers when you receive a 429 response code.

### Payload
```json
{
  "tag": "myword",
  "num": 123
}
```
num is the number of the comic to add the tag to.

### Returns
Response 204
[Empty]

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
# CDN Endpoints

## POST /api/cdn
* Requires an idevision API token with the `cdn` permission group

This endpoint allows you to upload content to the idevision cdn. 

### Ratelimit
6 requests per 7 seconds (6/7).
Exceeding this api by double (12/60) will result in an automatic api ban and disabling of your account.
Please follow the ratelimit-retry-after headers when you receive a 429 response code.

### Optional query parameters
- name: specifies the name of the file. Requires the `cdn.manage` permission to be effective
- node: specifies the cdn node to use. Requires the `cdn.manage` permission to be effective

### Example payload
This endpoint expects either a multipart form containing the image to upload, or a bytes stream of the file.
You should pass a `File-Name` header that specifies the name of the file, as the file extension will be pulled from this header.
It will default to .jpg if no `File-Name` header is passed.

### Returns
Response 201
```json
{
    "url": "https://cdn.idevision.net/node/slug",
    "slug": "somename.filetype",
    "node": "node the file is on"
}
```
___

## GET /api/cdn
This endpoint fetches basic statistics on the cdn.

### Ratelimit
20 requests per 60 seconds (20/60s).
Exceeding this api by double (40/60) will result in an automatic api ban (and disabling of your account, if you are using an API token). If you are using an API token, the rates above are doubled.
Please follow the ratelimit-retry-after headers when you receive a 429 response code.

### Returns
```json
{
    "upload_count": 1234,
    "uploaded_today": 1234,
    "last_uploaded": "https://cdn.idevision.net/node/slug"
}
```
___

## GET /api/cdn/{node}/{slug}
* Requires an idevision api token with the `cdn` permission group

Fetches info on a specific upload.

### Ratelimit
30 requests per 60 seconds (30/60s).
Exceeding this api by double (60/60) will result in an automatic api ban and disabling of your account.
Please follow the ratelimit-retry-after headers when you receive a 429 response code.

### Response
Response 200
```json
{
  "url": "https://cdn.idevision.net/node/slug",
  "timestamp": 12345,
  "author": "tom",
  "views": 5,
  "node": "node",
  "size": 12345
}
```
size is in bytes
___

## DELETE /api/cdn/{node}/{slug}
* Requires an idevision api token with the `cdn` permission group

Deletes a file from the cdn. If you do not have the `cdn.manage` permission group, you may only delete your own images.

### Ratelimit
14 requests per 60 seconds (14/60s).
Exceeding this api by double (10/30) will result in an automatic api ban and disabling of your account.
Please follow the ratelimit-retry-after headers when you receive a 429 response code.

### Returns
Response 204
> No content.

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