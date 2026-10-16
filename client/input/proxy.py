import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

# headers that describe one connection, not the content; they must not cross the proxy
HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "transfer-encoding", "upgrade",
}
METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"]


def build_proxy_router(server_url, transport=None):
    router = APIRouter()
    client = httpx.AsyncClient(
        base_url=server_url, transport=transport, follow_redirects=False, timeout=httpx.Timeout(10, read=None)
    )

    @router.api_route("/{path:path}", methods=METHODS, include_in_schema=False)
    async def forward(path: str, request: Request):
        # rebuild the URL from the raw bytes so encoded paths and queries reach the server unchanged
        target = request.scope.get("raw_path", request.url.path.encode()).decode("latin-1")
        query = request.scope.get("query_string", b"").decode("latin-1")
        if query:
            target = f"{target}?{query}"
        headers = [(k, v) for k, v in request.headers.raw if k.decode("latin-1").lower() not in HOP_BY_HOP | {"host"}]
        upstream_request = client.build_request(request.method, target, headers=headers, content=await request.body())
        try:
            upstream = await client.send(upstream_request, stream=True)
        except httpx.HTTPError:
            return JSONResponse({"detail": "server unreachable"}, status_code=502)

        # raw bytes keep content-encoding, content-length and content-range valid for the client
        response = StreamingResponse(upstream.aiter_raw(), status_code=upstream.status_code,
                                     background=BackgroundTask(upstream.aclose))
        response.raw_headers = [
            (k.encode("latin-1"), v.encode("latin-1"))
            for k, v in upstream.headers.multi_items() if k.lower() not in HOP_BY_HOP
        ]
        return response

    return router
