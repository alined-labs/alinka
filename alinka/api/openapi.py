"""Print the API's OpenAPI schema; `make openapi` writes it to openapi.json."""

import json

from alinka.api.app import app


def main() -> None:
    print(json.dumps(app.openapi(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
