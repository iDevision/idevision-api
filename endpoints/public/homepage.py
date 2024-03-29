import aiohttp_jinja2
from aiohttp import web

from utils import handler, app

router = web.RouteTableDef()

def setup(app):
    app.add_routes(router)

@router.post("/api/homepage")
@handler.ratelimit(5, 30)
async def home_urls(request: app.TypedRequest, conn):
    auth, admin = request.user['username'], "administrator" in request.user['permissions']
    try:
        data = await request.json()
    except:
        return web.Response(status=400, reason="Expected a json payload")

    user = data.get("user", auth) if admin else auth
    try:
        displayname = data['display_name']
        link1 = data['link1'], data['link1_name']
        link2 = data['link2'], data['link2_name']
        link3 = data['link3'], data['link3_name']
        link4 = data['link4'], data['link4_name']
    except KeyError as e:
        return web.Response(status=400, reason=f"Missing key '{e.args[0]}' in the request payload")

    await conn.execute("""INSERT INTO homepages VALUES ($1, $10, $2, $3, $4, $5, $6, $7, $8, $9)
    ON CONFLICT (username) DO UPDATE SET 
    display_name = $10,
    link1 = $2, link1_name = $3,
    link2 = $4, link2_name = $5,
    link3 = $6, link3_name = $7,
    link4 = $8, link4_name = $9
    """, user, *link1, *link2, *link3, *link4, displayname)

    return web.Response(status=204)

@router.get("/homepage")
@aiohttp_jinja2.template("static/homepage.html")
async def home(request: app.TypedRequest):
    usr = request.query.get("user", "Unknown")
    row = await request.app.db.fetchrow("SELECT * FROM homepages WHERE username = $1", usr)
    if not row:
        return {
            "name": "Unknown",
            "link1": "https://duckduckgo.com",
            "link2": "https://duckduckgo.com",
            "link3": "https://duckduckgo.com",
            "link4": "https://duckduckgo.com",
            "link1name": "DuckDuckGo",
            "link2name": "DuckDuckGo",
            "link3name": "DuckDuckGo",
            "link4name": "DuckDuckGo",
        }

    return {
        "name": row['display_name'],
        "link1": row['link1'],
        "link2": row['link2'],
        "link3": row['link3'],
        "link4": row['link4'],
        "link1name": row['link1_name'],
        "link2name": row['link2_name'],
        "link3name": row['link3_name'],
        "link4name": row['link4_name'],
    }
