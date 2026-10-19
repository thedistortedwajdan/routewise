"""Run the gateway: python -m routewise [--host H] [--port P]"""

import argparse

import uvicorn


def main() -> None:
    p = argparse.ArgumentParser(prog="routewise")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    a = p.parse_args()
    uvicorn.run("routewise.app:create_app", factory=True, host=a.host, port=a.port)


if __name__ == "__main__":
    main()
