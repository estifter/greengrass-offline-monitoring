import time
import logging
from typing import Dict, Set
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


def table_exists(db: Connection, name: str) -> bool:
    """Check that a table exists with the given columns"""

    cur = db.get_conn().cursor()
    check_tbl_sql = f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{name}';"
    cur.execute(check_tbl_sql)
    return len(cur.fetchall()) != 0


def fields_match(db: Connection, name: str, fields: Dict[str, str]) -> bool:
    """Check that a table exists with the given columns"""

    cur = db.get_conn().cursor()
    check_fields_sql = f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{name}';"
    cur.execute(check_fields_sql)
    # postgres columns are all lowercase, fields may not be
    lowered_fields = {k.lower(): v for k, v in fields.items()}
    existing_fields = {
        r[0]: r[1] for r in cur.fetchall() if r[0] in lowered_fields.keys()
    }  # ignore extra cols
    return lowered_fields == existing_fields


def create_table(db: Connection, name: str, fields: Dict[str, str]) -> None:
    """Validate and create table when request is sent."""

    query = None
    if table_exists(db, name):
        if fields_match(db, name, fields):
            logging.info(f"table {name} exists with same fields. using existing {name}")
            return
        else:
            logging.info(
                f"table {name} exists with different fields. altering existing {name}"
            )
            query = (
                f"ALTER TABLE {name} "
                + ",".join(
                    [f"ADD COLUMN IF NOT EXISTS {n} {t}" for n, t in fields.items()]
                )
                + ",".join([f"ALTER COLUMN {n} TYPE {t}" for n, t in fields.items()])
                + ";"
            )

    else:
        logging.info(f"table {name} does not exist. creating {name}")
        query = (
            f"CREATE TABLE {name} ("
            + ", ".join([f"{n} {t}" for n, t in fields.items()])
            + ");"
        )

    conn = db.get_conn()
    cur = conn.cursor()
    cur.execute(query)
    conn.commit()


def quote_str_for_sql(value):
    return f"'{value}'"


def prepare_insert(table_name: str, datapoint: Dict, expected_fields: Set[str]):
    given_fields = set()
    for k in datapoint.keys():
        if k not in expected_fields:
            logging.debug(f"field {k} not in database, will be ignored")
        else:
            given_fields.add(k)

    if expected_fields != given_fields:
        logging.error(f"expected missing fields {expected_fields - given_fields}")

    logging.debug(datapoint)
    logging.debug(given_fields)
    return (
        f"INSERT INTO {table_name} ("
        + ",".join(given_fields)
        + ") VALUES ("
        + ",".join([quote_str_for_sql(datapoint[f]) for f in given_fields])
        + ");"
    )


def insert_telemetry(
    db: Connection, table_name: str, data: Dict, expected_fields: Set[str]
) -> None:
    """Insert telemetry to Postgres."""

    conn = db.get_conn()
    cur = conn.cursor()

    for point in data:
        insert_sql = prepare_insert(table_name, point, expected_fields)
        logging.info(f"executing INSERT into table {table_name}")
        logging.debug(f"sql: {insert_sql}")
        try:
            cur.execute(insert_sql)
            conn.commit()
        except psycopg2.errors.InFailedSqlTransaction:
            conn.rollback()
