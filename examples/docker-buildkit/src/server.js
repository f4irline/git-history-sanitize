import http from 'node:http'

http.createServer((_request, response) => {
  response.writeHead(200, { 'content-type': 'application/json' })
  response.end(JSON.stringify({ status: 'ok' }))
}).listen(process.env.PORT ?? 3000)
