from aiohttp import web
import io
import random

choices = list("qwertyuiopadfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM1234567890")

app = web.Application()
router = web.RouteTableDef()

with open("authorization.txt") as f:
    auth = f.read()

@router.post("/media")
async def post_media(request: web.Request):
    authorization = request.headers.get("Authorization")
    if authorization != auth:
        return web.Response(text="403 Unauthorized", status=403)

    data = await request.post()
    file = data['upload']
    extension = file.filename.split(".").pop()
    new_name = "".join([random.choice(choices) for i in range(3)]) + f".{extension}"
    buffer = io.FileIO(f"media/{new_name}", mode="w")
    buffer.write(file.file.read())
    buffer.close()
    return web.json_response({"key": new_name}, status=200)

router.static("/media", "media")

app.add_routes(router)
web.run_app(
    app,
    host="media.idevision.net",
    port=80
)