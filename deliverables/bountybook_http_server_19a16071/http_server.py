"""Minimal single-connection-at-a-time HTTP/1.1 server.

This submission intentionally uses only the standard-library modules allowed by
the bounty specification: socket, threading, and re.
"""

import re
import socket
import threading


_REQUEST_LINE = re.compile(r"^(GET|POST)\s+(\S+)\s+HTTP/1\.[01]$")
_REASONS = {
    200: "OK",
    201: "Created",
    204: "No Content",
    400: "Bad Request",
    404: "Not Found",
    405: "Method Not Allowed",
    500: "Internal Server Error",
}


class Request:
    def __init__(self, method, path, headers, body):
        self.method = method
        self.path = path
        self.headers = headers
        self.body = body


class Response:
    def __init__(self, status, content_type, body):
        self.status = int(status)
        self.content_type = str(content_type)
        self.body = body

    def to_bytes(self):
        body = self.body if isinstance(self.body, bytes) else str(self.body).encode("utf-8")
        reason = _REASONS.get(self.status, "Unknown")
        head = (
            f"HTTP/1.1 {self.status} {reason}\r\n"
            f"Content-Type: {self.content_type}\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("ascii")
        return head + body


class HTTPServer:
    def __init__(self, host, port):
        self.host = host
        self.port = int(port)
        self._routes = {}
        self._socket = None
        self._ready = threading.Event()
        self._stopped = threading.Event()

    def route(self, path, method="GET"):
        method = str(method).upper()
        if method not in {"GET", "POST"}:
            raise ValueError("method must be GET or POST")
        if not str(path).startswith("/"):
            raise ValueError("route path must start with /")

        def register(handler):
            self._routes[(method, str(path))] = handler
            return handler

        return register

    def wait_until_ready(self, timeout=None):
        return self._ready.wait(timeout)

    def stop(self):
        self._stopped.set()
        listener = self._socket
        if listener is not None:
            try:
                listener.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                listener.close()
            except OSError:
                pass

    def _read_request(self, connection):
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = connection.recv(4096)
            if not chunk:
                raise ValueError("incomplete HTTP headers")
            data += chunk
            if len(data) > 65536:
                raise ValueError("HTTP headers too large")

        raw_head, body = data.split(b"\r\n\r\n", 1)
        lines = raw_head.decode("iso-8859-1").split("\r\n")
        match = _REQUEST_LINE.match(lines[0])
        if not match:
            raise ValueError("invalid or unsupported request line")

        method, target = match.groups()
        headers = {}
        for line in lines[1:]:
            if ":" not in line:
                raise ValueError("invalid HTTP header")
            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()

        try:
            content_length = int(headers.get("content-length", "0"))
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if content_length < 0 or content_length > 10_000_000:
            raise ValueError("invalid Content-Length")
        while len(body) < content_length:
            chunk = connection.recv(min(4096, content_length - len(body)))
            if not chunk:
                raise ValueError("incomplete HTTP body")
            body += chunk

        path = target.split("?", 1)[0]
        return Request(method, path, headers, body[:content_length].decode("utf-8", errors="replace"))

    def _serve_connection(self, connection):
        try:
            request = self._read_request(connection)
            handler = self._routes.get((request.method, request.path))
            if handler is None:
                response = Response(404, "text/plain; charset=utf-8", "Not Found")
            else:
                try:
                    response = handler(request)
                    if not isinstance(response, Response):
                        raise TypeError("route handler must return Response")
                except Exception:
                    response = Response(500, "text/plain; charset=utf-8", "Internal Server Error")
        except ValueError:
            response = Response(400, "text/plain; charset=utf-8", "Bad Request")
        connection.sendall(response.to_bytes())

    def start(self, timeout=None):
        self._stopped.clear()
        self._ready.clear()
        timer = None
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket = listener
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind((self.host, self.port))
            self.port = listener.getsockname()[1]
            listener.listen(5)
            self._ready.set()
            if timeout is not None:
                timer = threading.Timer(float(timeout), self.stop)
                timer.daemon = True
                timer.start()
            while not self._stopped.is_set():
                try:
                    connection, _ = listener.accept()
                except OSError:
                    break
                with connection:
                    self._serve_connection(connection)
        finally:
            if timer is not None:
                timer.cancel()
            self._stopped.set()
            self._ready.set()
            try:
                listener.close()
            except OSError:
                pass
            if self._socket is listener:
                self._socket = None

