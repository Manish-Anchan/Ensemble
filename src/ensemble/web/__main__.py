import sys
import os
import argparse
import uvicorn


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


def main():
    parser = argparse.ArgumentParser(description="Ensemble Audio Drama Web Studio")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload on file changes")
    args = parser.parse_args()

    port = args.port
    if args.port == 8000 and is_port_in_use(8000):
        port = 8080
        print(f"⚠️  Port 8000 is already in use by another service. Switching to port {port}.")

    print(f"🎭 Starting Ensemble Audio Drama Studio at http://localhost:{port}")
    uvicorn.run("ensemble.web.app:app", host=args.host, port=port, reload=args.reload)


if __name__ == "__main__":
    main()
