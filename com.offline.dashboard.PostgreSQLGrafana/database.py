import time
import logging
from dataclasses import dataclass

import psycopg2
import psycopg2.errors

logging.basicConfig(level=logging.INFO)


@dataclass
class Credentials:
    database: str
    hostname: str
    port: str
    username: str
    password: str


class Connection:
    """Thin wrapper around psycopg2.connection that will retry connecting with exponential backoff"""

    def __init__(self, creds: Credentials) -> None:
        self.creds = creds
        self._conn = self._connect()

    def get_conn(self):
        if self._conn is not None and not self._conn.closed:
            return self._conn

        self._conn = self._connect()
        return self._conn

    def close(self):
        if self._conn is not None and not self._conn.closed:
            self._conn.close()

    def _connect(self):
        i = 1
        conn = None
        while conn is None:
            if i >= 512:
                logging.error(f"could not connect to database {self.creds.database}")
                exit(1)

            try:
                conn = psycopg2.connect(
                    dbname=self.creds.database,
                    host=self.creds.hostname,
                    port=str(self.creds.port),
                    user=self.creds.username,
                    password=self.creds.password,
                )
            except Exception:
                logging.info(
                    f"couldn't connect to database. retry in {i}s", exc_info=True
                )
                time.sleep(i)
                i *= 2
        return conn
