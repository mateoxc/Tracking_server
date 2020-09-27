
import http.server
import socketserver


class MyHttpRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.path = 'Map.html'
        return http.server.SimpleHTTPRequestHandler.do_GET(self)

# Create an object of the above class
handler_object = MyHttpRequestHandler

PORT2 = 8000
my_server = socketserver.TCPServer(("", PORT2), handler_object)

# Star the server
my_server.serve_forever()