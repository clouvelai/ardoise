"""python -m ardoise_api"""

import os

import uvicorn

from ardoise_api.main import app


def main() -> None:
    host = os.environ.get("ARDOISE_API_HOST", "127.0.0.1")
    port = int(os.environ.get("ARDOISE_API_PORT", "8787"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
