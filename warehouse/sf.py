"""Run SQL against Snowflake using key-pair auth from .env.

    uv run python -m warehouse.sf "select current_role()"     # inline SQL
    uv run python -m warehouse.sf -f warehouse/sql/01_foundation.sql   # a file

Files may contain many statements and use {{ENV_VAR}} placeholders, which are
filled from the environment (so secrets never live in the .sql files).
"""

import os
import re
import sys
from pathlib import Path

import snowflake.connector
from dotenv import load_dotenv


def connect(**overrides):
    load_dotenv()
    params = dict(account=os.environ["SNOWFLAKE_ACCOUNT"], user=os.environ["SNOWFLAKE_USER"])
    if os.environ.get("SNOWFLAKE_PRIVATE_KEY"):
        # CI: the key's PEM contents come from a secret.
        from cryptography.hazmat.primitives import serialization

        key = serialization.load_pem_private_key(os.environ["SNOWFLAKE_PRIVATE_KEY"].encode(), password=None)
        params["private_key"] = key.private_bytes(
            serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    else:
        params["private_key_file"] = str(Path(os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"]).expanduser())
    params.update(overrides)
    return snowflake.connector.connect(**params)


def render(sql: str) -> str:
    return re.sub(r"\{\{(\w+)\}\}", lambda m: os.environ[m.group(1)], sql)


def run(sql: str) -> None:
    with connect() as conn:
        for cur in conn.execute_string(render(sql), remove_comments=True):
            rows = cur.fetchall()
            first = cur.query.strip().splitlines()[0][:70]
            if first.upper().startswith("COPY INTO"):
                # One result row per file; summarize instead of printing them all.
                if rows and cur.description and cur.description[0][0].lower() == "file":
                    loaded = sum(r[3] for r in rows)
                    bad = [r for r in rows if r[1] != "LOADED"]
                    print(f"ok  {first}: {len(rows)} new files, {loaded} rows")
                    for r in bad:
                        print(f"    !! {r[0]}: {r[1]} {r[6]}")
                    if bad:
                        raise SystemExit(1)
                else:
                    print(f"ok  {first}: no new files")
                continue
            if cur.description and rows and not first.upper().startswith(("CREATE", "GRANT", "ALTER", "USE")):
                cols = [d[0] for d in cur.description]
                print(f"-- {first}")
                print("   " + " | ".join(cols))
                for r in rows[:50]:
                    print("   " + " | ".join(str(v) for v in r))
            else:
                print(f"ok  {first}")


if __name__ == "__main__":
    load_dotenv()
    args = sys.argv[1:]
    run(Path(args[1]).read_text() if args[:1] == ["-f"] else " ".join(args))
