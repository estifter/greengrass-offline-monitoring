import time
import logging
import json
from argparse import ArgumentParser
from typing import Tuple, Union, Dict

import awscrt.mqtt
from awscrt.mqtt import QoS
from awsiot import mqtt_connection_builder
from awsiot.greengrasscoreipc.clientv2 import GreengrassCoreIPCClientV2
from awsiot.greengrasscoreipc.model import SubscriptionResponseMessage


logging.basicConfig(level=logging.INFO)


def parse_args():
    parser = ArgumentParser(description="Send the output from a command over MQTT")
    parser.add_argument(
        "--topics",
        required=True,
        help="A map of topics to relay in the form local:remote",
    )
    parser.add_argument(
        "--hostname_path",
        required=True,
        help="The path to a file containing the hostname of the broker",
    )
    parser.add_argument(
        "--port_path",
        required=True,
        help="The path to a file containing the port of the broker",
    )
    parser.add_argument(
        "--broker_cert_path",
        required=True,
        help="The path to the broker's CA certificate",
    )
    parser.add_argument(
        "--cert_path",
        required=True,
        help="Path to the X.509 certificate of the client device",
    )
    parser.add_argument(
        "--key_path",
        required=True,
        help="Path to the X.509 certificate's private key",
    )
    parser.add_argument(
        "--thing_name",
        required=True,
        help="The AWS IoT thing name for use as client ID for MQTT",
    )
    return parser.parse_args()


def remote_connection(
    endpoint: str,
    port: int,
    cert_path: str,
    key_path: str,
    ca_path: str,
    client_id: str,
) -> Union[awscrt.mqtt.Connection, None]:
    def on_conn_success(**_):
        logging.info(f"connected to {hostname}:{port} as {client_id}")

    def on_conn_failure(**_):
        logging.error(f"error: failed to connect to {hostname}:{port} as {client_id}")

    def on_conn_close(**_):
        logging.error(f"closed connection to {hostname}:{port} as {client_id}")

    remote_client = mqtt_connection_builder.mtls_from_path(
        endpoint=endpoint,
        port=port,
        cert_filepath=cert_path,
        pri_key_filepath=key_path,
        ca_filepath=ca_path,
        client_id=client_id,
        clean_session=False,
        on_connection_success=on_conn_success,
        on_connection_failure=on_conn_failure,
        on_connection_closed=on_conn_close,
        keep_alive_secs=30,
    )

    # this will raise an error if connection fails
    try:
        remote_client.connect().result()
    except:
        return None
    return remote_client


def remote_connection_with_retry(
    endpoint: str,
    port: int,
    cert_path: str,
    key_path: str,
    ca_path: str,
    client_id: str,
    retries: int = 10,
) -> awscrt.mqtt.Connection:
    for pwr in range(retries):
        conn = remote_connection(
            endpoint, port, cert_path, key_path, ca_path, client_id
        )
        if not conn:
            time.sleep(2**pwr)
            logging.info(f"could not connect: retrying in {2**pwr}s")
            continue
        return conn
    raise ConnectionError(f"could not connect to broker at {endpoint}:{port}")


def safe_get_message_and_topic(
    e: SubscriptionResponseMessage,
) -> Tuple[bytes, str]:
    if e.binary_message:
        if e.binary_message.message and e.binary_message.context:
            topic = str(e.binary_message.context.topic)
            return e.binary_message.message, topic
    elif e.json_message:
        if e.json_message.message and e.json_message.context:
            topic = str(e.json_message.context.topic)
            return json.dumps(e.json_message.message).encode(), topic
    raise ValueError(f"message must have both a message and topic field: {e}")


def relay_messages(
    local_client: GreengrassCoreIPCClientV2,
    remote_client: awscrt.mqtt.Connection,
    topic_map: Dict[str, str],
):
    def on_event(event: SubscriptionResponseMessage, local_topic: str):
        try:
            message, local_topic = safe_get_message_and_topic(event)
            remote_topic = topic_map[local_topic]

            logging.debug(f"start relay {local_topic} -> {remote_topic} : {message}")
            resp, _ = remote_client.publish(remote_topic, message, QoS.AT_LEAST_ONCE)
            resp.result()
            logging.info(f"relay {local_topic} -> {remote_topic}")
        except Exception as e:
            logging.error(f"failed relay from {local_topic}")
            logging.debug(e)

    def on_error(topic: str) -> bool:
        logging.error(f"error connecting to IPC client on topic {topic}")
        return False

    for t in topic_map.keys():
        logging.debug(f"to be relayed: {t}")
        local_client.subscribe_to_topic(
            topic=t,
            on_stream_event=lambda e: on_event(e, t),
            on_stream_error=lambda _: on_error(t),
        )


if __name__ == "__main__":
    args = parse_args()
    all_topics = json.loads(args.topics)

    with open(args.hostname_path) as f:
        hostname = f.read().strip()
    with open(args.port_path) as f:
        port = int(f.read().strip())

    topic_map = {x["From"]: x["To"] for x in all_topics}
    local_client = GreengrassCoreIPCClientV2()
    logging.info("attempting to connect to remote MQTT broker")
    remote_client = remote_connection_with_retry(
        hostname,
        port,
        args.cert_path,
        args.key_path,
        args.broker_cert_path,
        args.thing_name,
    )

    logging.debug(f"topic map: {topic_map}")
    try:
        relay_messages(local_client, remote_client, topic_map)
        while True:
            time.sleep(1)
    except Exception as e:
        logging.error(e)

    remote_client.disconnect().result()
