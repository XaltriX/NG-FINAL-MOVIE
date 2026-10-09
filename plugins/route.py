from aiohttp import web

routes = web.RouteTableDef()


# Heroku needs a web process answering on $PORT. Streaming/watch pages were removed,
# so only the health route is left.
@routes.get("/", allow_head=True)
async def root_route_handler(request):
    return web.json_response("Newmovie_sbot")
