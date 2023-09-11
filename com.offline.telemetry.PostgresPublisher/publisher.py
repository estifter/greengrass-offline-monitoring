import time
import json
import logging
import argparse
from typing import Set, Tuple

from awsiot.greengrasscoreipc.clientv2 import GreengrassCoreIPCClientV2
from awsiot.greengrasscoreipc.model import (
    BinaryMessage,
    PublishMessage,
    SubscriptionResponseMessage,
)

import database

logging.basicConfig(level=logging.INFO)

config_req_topic = "greengrass/postgresql/config/request"
config_resp_topic = "greengrass/postgresql/config/response"

table_name = "telemetry"
metric_fields = {
    "TS": "bigint",
    "N": "text",
    "NS": "text",
    "U": "text",
    "A": "text",
    "V": "text",
    "thing_name": "text",
}


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--telemetry_topic", type=str, required=True)
    parser.add_argument("--postgresql_secret_arn", type=str, required=True)
    return parser.parse_args()


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


def get_postgres_credentials(
    ipc_client: GreengrassCoreIPCClientV2, secret_arn: str
) -> database.Credentials:
    """Retrieve credentials from the PostgreSQL component via IPC"""

    creds = None

    def on_resp(e: SubscriptionResponseMessage):
        nonlocal creds
        if e.json_message and e.json_message.message:
            config_json = e.json_message.message
            logging.info(f"got configuration response: {config_json}")
            username, password = get_postgres_user_and_pass(ipc_client, secret_arn)
            creds = database.Credentials(
                database=config_json["database"],
                hostname=config_json["hostname"],
                port=config_json["port"],
                username=username,
                password=password,
            )
        else:
            raise ValueError(f"configuration response formed incorrectly: {str(e)}")

    logging.info("listening for postgresql configuration response")
    ipc_client.subscribe_to_topic(topic=config_resp_topic, on_stream_event=on_resp)

    logging.info("requesting postgresql configuration")
    ipc_client.publish_to_topic(
        topic=config_req_topic,
        publish_message=PublishMessage(
            binary_message=BinaryMessage(message="config request")
        ),
    )

    while creds is None:
        time.sleep(5)
        logging.info("retrying postgresql configuration request")
        ipc_client.publish_to_topic(
            topic=config_req_topic,
            publish_message=PublishMessage(
                binary_message=BinaryMessage(message="config request")
            ),
        )
    return creds


def send_telemetry(
    db: database.Connection, table_name: str, telemetry, cols: Set[str]
) -> None:
    """Relay Greengrass system telemetry from Greengrass to Postgres."""

    database.insert_telemetry(db, table_name, telemetry, cols)


def relay_telemetry(
    ipc_client: GreengrassCoreIPCClientV2,
    db: database.Connection,
    telemetry_topic: str,
    table_name: str,
    cols: Set[str],
):
    def on_tel_event(e: SubscriptionResponseMessage):
        if e.binary_message and e.binary_message.message:
            logging.debug(f"received message: {str(e.binary_message.message)}")
            telemetry_data = json.loads(e.binary_message.message.decode())
            send_telemetry(db, table_name, telemetry_data, cols)
        else:
            logging.error(f"message cannot be None: {e}")

    logging.info(f"listening for telemetry on topic {telemetry_topic}")
    ipc_client.subscribe_to_topic(topic=telemetry_topic, on_stream_event=on_tel_event)


if __name__ == "__main__":
    args = parse_arguments()

    client = GreengrassCoreIPCClientV2()
    creds = get_postgres_credentials(client, args.postgresql_secret_arn)
    db = database.Connection(creds)

    database.create_table(db, table_name, metric_fields)

    try:
        relay_telemetry(
            client, db, args.telemetry_topic, table_name, set(metric_fields.keys())
        )

        while True:
            time.sleep(5)
    except Exception as e:
        db.close()
        raise e
