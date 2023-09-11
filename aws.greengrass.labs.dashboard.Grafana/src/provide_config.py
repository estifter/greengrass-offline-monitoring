import time
import logging
import argparse

from awsiot.greengrasscoreipc.clientv2 import GreengrassCoreIPCClientV2
from awsiot.greengrasscoreipc.model import (
    SubscriptionResponseMessage,
    JsonMessage,
    PublishMessage,
)

logging.basicConfig(level=logging.INFO)

config_req_topic = "greengrass/grafana/config/request"
config_resp_topic = "greengrass/grafana/config/response"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--grafana_port", type=str, required=True)
    parser.add_argument("--grafana_hostname", type=str, required=True)
    parser.add_argument("--grafana_server_protocol", type=str, required=True)
    return parser.parse_args()


def listen_for_config_requests(
    ipc_client: GreengrassCoreIPCClientV2, hostname: str, port: str, protocol: str
):
    def on_event(_: SubscriptionResponseMessage):
        config_json = {"protocol": protocol, "hostname": hostname, "port": port}
        msg = JsonMessage(message=config_json)
        logging.info(f"publishing configuration response: {config_json}")
        ipc_client.publish_to_topic(
            topic=config_resp_topic,
            publish_message=PublishMessage(json_message=msg),
        )

    logging.info("listening for postgresql configuration requests")
    ipc_client.subscribe_to_topic(topic=config_req_topic, on_stream_event=on_event)


if __name__ == "__main__":
    args = parse_args()

    client = GreengrassCoreIPCClientV2()
    listen_for_config_requests(
        client, args.grafana_hostname, args.grafana_port, args.grafana_server_protocol
    )

    while True:
        time.sleep(5)
