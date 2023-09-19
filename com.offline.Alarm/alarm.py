import json
import time
from argparse import ArgumentParser
import subprocess

import boto3
from awsiot.greengrasscoreipc.clientv2 import GreengrassCoreIPCClientV2
from awsiot.greengrasscoreipc.model import SubscriptionResponseMessage


parser = ArgumentParser(__name__)
parser.add_argument("--sns_topic", required=True)
parser.add_argument("--on_alarm_command")

telemetry_topic = "injected/greengrass/telemetry"

already_alarmed = set()


def send_to_sns(client, topic_arn: str, message: str):
    client.publish(TopicArn=topic_arn, Message=message)


def check_telemetry(
    ipc_client: GreengrassCoreIPCClientV2, boto_client, topic_arn, on_alarm_command
):
    def on_tel_event(e: SubscriptionResponseMessage):
        telemetry_data = None
        if e.binary_message and e.binary_message.message:
            telemetry_data = json.loads(e.binary_message.message.decode())

        broken_components = set()
        if telemetry_data:
            for point in telemetry_data:
                if point["NS"] == "ComponentStatus" and point["V"] == "BROKEN":
                    broken_components.add(point["N"])

        if len(broken_components - already_alarmed) > 0:
            already_alarmed.update(broken_components)
            if on_alarm_command:
                proc = subprocess.run(on_alarm_command, shell=True, capture_output=True)
                print(
                    "alarm output:",
                    {"stdout": proc.stdout.decode(), "stderr": proc.stderr.decode()},
                )

            message = {
                "source": "com.offline.Alarm",
                "components_broken": list(broken_components),
            }
            print(f"sending message: {message}")
            send_to_sns(boto_client, topic_arn, json.dumps(message))

    ipc_client.subscribe_to_topic(topic=telemetry_topic, on_stream_event=on_tel_event)


if __name__ == "__main__":
    args = parser.parse_args()
    client = boto3.client("sns")
    topic_arn = args.sns_topic

    check_telemetry(
        GreengrassCoreIPCClientV2(), client, topic_arn, args.on_alarm_command
    )
    timer = 0
    while True:
        # every 5 minutes we reset the alarm
        if timer % 300 == 0:
            already_alarmed.clear()
        time.sleep(1)
        timer += 1
