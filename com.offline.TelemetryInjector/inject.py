import os
import sys
import json
import logging
import time
from typing import Dict, List

import health
from awsiot.greengrasscoreipc.clientv2 import GreengrassCoreIPCClientV2
from awsiot.greengrasscoreipc.model import (
    BinaryMessage,
    PublishMessage,
    SubscriptionResponseMessage,
)


logging.basicConfig(level=logging.INFO)


telemetry_topic = "$local/greengrass/telemetry"


def inject_state_to_telemetry(telemetry_data: List[Dict], thing_name: str):
    component_states = health.get_all_components_states()
    for c in component_states:
        telemetry_data.append(
            {
                "NS": "ComponentStatus",
                "N": c["name"],
                "U": "None",
                "A": "None",
                "V": c["state"],
                "TS": time.time_ns() // 1_000_000,  # time in ms
            }
        )

    for point in telemetry_data:
        point["thing_name"] = thing_name

    return telemetry_data


def inject_and_send_telemetry(
    ipc_client: GreengrassCoreIPCClientV2,
    telemetry_data: List[Dict[str, str]],
    thing_name: str,
    injected_topic: str,
):
    new_telemetry = inject_state_to_telemetry(telemetry_data, thing_name)
    msg = PublishMessage(
        binary_message=BinaryMessage(message=json.dumps(new_telemetry))
    )
    logging.info(f"publishing updated telemetry on topic {injected_topic}")
    logging.debug(new_telemetry)
    ipc_client.publish_to_topic(topic=injected_topic, publish_message=msg)


def relay_telemetry(
    ipc_client: GreengrassCoreIPCClientV2, thing_name: str, injected_topic: str
):
    def on_tel_event(e: SubscriptionResponseMessage):
        if e.binary_message and e.binary_message.message:
            telemetry_data = json.loads(e.binary_message.message.decode())
            inject_and_send_telemetry(
                ipc_client, telemetry_data, thing_name, injected_topic
            )
        else:
            logging.error(f"message cannot be None: {e}")

    logging.info(f"listening for telemetry on topic {telemetry_topic}")
    ipc_client.subscribe_to_topic(topic=telemetry_topic, on_stream_event=on_tel_event)


if __name__ == "__main__":
    injected_telemetry_topic = sys.argv[1]
    thing_name = os.environ["AWS_IOT_THING_NAME"]

    relay_telemetry(GreengrassCoreIPCClientV2(), thing_name, injected_telemetry_topic)

    while True:
        time.sleep(3)
