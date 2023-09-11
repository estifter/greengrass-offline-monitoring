import dataclasses
import time
import json
import logging
import argparse
from typing import Dict, Tuple, Union

import requests
from awsiot.greengrasscoreipc.clientv2 import GreengrassCoreIPCClientV2
from awsiot.greengrasscoreipc.model import (
    BinaryMessage,
    PublishMessage,
    SubscriptionResponseMessage,
)

import database

logging.basicConfig(level=logging.DEBUG)

postgres_config_req_topic = "greengrass/postgresql/config/request"
postgres_config_resp_topic = "greengrass/postgresql/config/response"
grafana_config_req_topic = "greengrass/grafana/config/request"
grafana_config_resp_topic = "greengrass/grafana/config/response"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--postgresql_secret_arn", type=str, required=True)
    parser.add_argument("--grafana_secret_arn", type=str, required=True)
    return parser.parse_args()


def datasource_json(db_creds: database.Credentials) -> Dict:
    return {
        "access": "proxy",
        "name": "PostgreSQL",
        "type": "postgres",
        "url": f"{db_creds.hostname}:{db_creds.port}",
        "user": db_creds.username,
        "secureJsonData": {"password": db_creds.password},
        "isDefault": True,
        "jsonData": {
            "database": db_creds.database,
            "sslmode": "disable",
            "maxOpenConns": 100,
            "maxIdleConns": 100,
            "maxIdleConnsAuto": True,
            "connMaxLifetime": 14400,
            "timescaledb": False,
            "postgresVersion": 1500,
        },
    }


def get_secret_string(ipc_client: GreengrassCoreIPCClientV2, arn: str) -> str:
    resp = ipc_client.get_secret_value(secret_id=arn)
    if resp and resp.secret_value and resp.secret_value.secret_string:
        return resp.secret_value.secret_string
    raise ValueError(f"could not retrieve secret_string for arn {arn}")


def get_postgres_user_and_pass(
    ipc_client: GreengrassCoreIPCClientV2, secret_arn: str
) -> Tuple[str, str]:
    try:
        secret_json = json.loads(get_secret_string(ipc_client, secret_arn))
        return secret_json["POSTGRES_USER"], secret_json["POSTGRES_PASSWORD"]
    except ValueError as e:
        raise ValueError(
            f"could not retrieve username/password for PostgreSQL from SecretsManager: {e}"
        )


def get_grafana_user_and_pass(
    ipc_client: GreengrassCoreIPCClientV2, secret_arn: str
) -> Tuple[str, str]:
    try:
        secret_json = json.loads(get_secret_string(ipc_client, secret_arn))
        return secret_json["grafana_username"], secret_json["grafana_password"]
    except ValueError as e:
        raise ValueError(
            f"could not retrieve username/password for Grafana from SecretsManager: {e}"
        )


def get_postgres_credentials(
    ipc_client: GreengrassCoreIPCClientV2, secret_arn: str, use_container_name: bool
) -> database.Credentials:
    """Retrieve credentials from the PostgreSQL component via IPC"""

    creds = None

    def on_resp(e: SubscriptionResponseMessage):
        nonlocal creds
        if e.json_message and e.json_message.message:
            config_json = e.json_message.message
            logging.info(f"got configuration response: {config_json}")
            username, password = get_postgres_user_and_pass(ipc_client, secret_arn)
            hostname = (
                config_json["container_name"]
                if use_container_name
                else config_json["hostname"]
            )
            creds = database.Credentials(
                database=config_json["database"],
                port=config_json["port"],
                hostname=hostname,
                username=username,
                password=password,
            )
        else:
            raise ValueError(f"configuration response formed incorrectly: {str(e)}")

    logging.info("listening for postgresql configuration response")
    ipc_client.subscribe_to_topic(
        topic=postgres_config_resp_topic, on_stream_event=on_resp
    )

    logging.info("requesting postgresql configuration")
    ipc_client.publish_to_topic(
        topic=postgres_config_req_topic,
        publish_message=PublishMessage(
            binary_message=BinaryMessage(message="config request")
        ),
    )

    while creds is None:
        time.sleep(5)
        logging.info("retrying postgresql configuration request")
        ipc_client.publish_to_topic(
            topic=postgres_config_req_topic,
            publish_message=PublishMessage(
                binary_message=BinaryMessage(message="config request")
            ),
        )
    return creds


def get_grafana_credentials(
    ipc_client: GreengrassCoreIPCClientV2, secret_arn: str
) -> Dict[str, str]:
    """Retrieve credentials from the Grafana component via IPC"""

    config_json = None

    def on_resp(e: SubscriptionResponseMessage):
        nonlocal config_json
        if e.json_message and e.json_message.message:
            config_json = e.json_message.message
            logging.info(f"got configuration response: {config_json}")
            username, password = get_grafana_user_and_pass(ipc_client, secret_arn)
            config_json["username"] = username
            config_json["password"] = password
        else:
            raise ValueError(f"configuration response formed incorrectly: {str(e)}")

    logging.info("listening for grafana configuration response")
    ipc_client.subscribe_to_topic(
        topic=grafana_config_resp_topic, on_stream_event=on_resp
    )

    logging.info("requesting grafana configuration")
    ipc_client.publish_to_topic(
        topic=grafana_config_req_topic,
        publish_message=PublishMessage(
            binary_message=BinaryMessage(message="config request")
        ),
    )

    while config_json is None:
        time.sleep(5)
        logging.info("retrying grafana configuration request")
        ipc_client.publish_to_topic(
            topic=grafana_config_req_topic,
            publish_message=PublishMessage(
                binary_message=BinaryMessage(message="config request")
            ),
        )
    return config_json


def provision_readonly_user(
    db: database.Connection, username: str, password: str
) -> None:
    conn = db.get_conn()
    cur = conn.cursor()

    check_user_sql = f"SELECT 1 FROM pg_roles WHERE rolname='{username}'"
    cur.execute(check_user_sql)
    if len(cur.fetchall()) > 0:
        logging.info("using existing read-only user")
        return

    provision_user_sql = (
        f"CREATE USER {username} WITH PASSWORD '{password}';"
        f"ALTER DEFAULT PRIVILEGES FOR USER {db.creds.username} IN SCHEMA public "
        f"GRANT SELECT ON TABLES TO {username};"
        f"GRANT CONNECT ON DATABASE {db.creds.database} TO {username};"
        f"ALTER DEFAULT PRIVILEGES FOR USER {db.creds.username} IN SCHEMA public "
        f"GRANT SELECT ON TABLES TO {username};"
    )
    try:
        cur.execute(provision_user_sql)
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e


def get_existing_datasource(base_url: str, auth: Tuple[str, str]) -> Union[str, None]:
    url = f"{base_url}/api/datasources"
    logging.debug("attempting to list grafana datasources")
    try:
        r = requests.get(url, auth=auth, headers={"Accept": "application/json"})
        json = r.json()
        r.raise_for_status()
        logging.debug("successfully listed datasources")
        logging.debug(r)
    except Exception as e:
        logging.error(f"could not get existing datasources: {e}")
        return

    for datasource in json:
        if datasource["type"] == "postgres":
            return datasource["uid"]


def update_existing_datasource(
    base_url: str, auth: Tuple[str, str], uid: str, db_creds: database.Credentials
):
    url = f"{base_url}/api/datasources/uid/{uid}"
    logging.debug("attempting to update postgresql datasource")
    try:
        r = requests.put(
            url,
            json=datasource_json(db_creds),
            auth=auth,
            headers={"Accept": "application/json"},
        )
        r.raise_for_status()
        logging.info("successfully updated postgresql datasource")
        logging.debug(r)
    except Exception as e:
        logging.error(f"could not update existing datasource: {e}")


def add_datasource(
    base_url: str, auth: Tuple[str, str], db_creds: database.Credentials
):
    url = f"{base_url}/api/datasources/"
    logging.debug("attempting to add postgresql datasource")
    try:
        r = requests.post(
            url,
            json=datasource_json(db_creds),
            auth=auth,
            headers={"Accept": "application/json"},
        )
        r.raise_for_status()
        logging.info("successfully added postgresql datasource")
        logging.debug(r)
    except Exception as e:
        logging.error(f"could not add postgresql datasource: {e}")


def configure_grafana_datasource(
    username: str,
    password: str,
    protocol: str,
    hostname: str,
    port: str,
    db_creds: database.Credentials,
):
    auth = (username, password)
    base_url = f"{protocol}://{hostname}:{port}"

    logging.info("configuring grafana datasource")
    existing = get_existing_datasource(base_url, auth)
    if existing is not None:
        update_existing_datasource(base_url, auth, existing, db_creds)
    else:
        add_datasource(base_url, auth, db_creds)


if __name__ == "__main__":
    args = parse_args()

    client = GreengrassCoreIPCClientV2()
    grafana_config = get_grafana_credentials(client, args.grafana_secret_arn)
    postgres_admin_creds = get_postgres_credentials(
        client, args.postgresql_secret_arn, use_container_name=False
    )
    db = database.Connection(postgres_admin_creds)

    postgres_readonly_creds = get_postgres_credentials(
        client, args.postgresql_secret_arn, use_container_name=True
    )
    provision_readonly_user(
        db, postgres_readonly_creds.username, postgres_readonly_creds.password
    )

    configure_grafana_datasource(
        grafana_config["username"],
        grafana_config["password"],
        grafana_config["protocol"],
        grafana_config["hostname"],
        grafana_config["port"],
        postgres_readonly_creds,
    )
