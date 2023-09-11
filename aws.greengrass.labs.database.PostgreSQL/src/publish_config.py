import logging

from awsiot.greengrasscoreipc.clientv2 import GreengrassCoreIPCClientV2
from awsiot.greengrasscoreipc.model import (
    SubscriptionResponseMessage,
    JsonMessage,
    PublishMessage,
)

from src.configuration import ComponentConfiguration
from src.container import ContainerManagement
from src.constants import DEFAULT_DB_NAME, DEFAULT_HOST_NAME


config_req_topic = "greengrass/postgresql/config/request"
config_resp_topic = "greengrass/postgresql/config/response"


class ConfigurationPublisher:
    def __init__(self):
        pass

    def listen_for_config_requests(
        self, ipc_client: GreengrassCoreIPCClientV2, container: ContainerManagement
    ):
        def on_event(_: SubscriptionResponseMessage):
            config_json = self._get_config_response_json(
                container.current_configuration
            )
            msg = JsonMessage(message=config_json)
            logging.info(f"publishing configuration response: {config_json}")
            ipc_client.publish_to_topic(
                topic=config_resp_topic,
                publish_message=PublishMessage(json_message=msg),
            )

        logging.info("listening for postgresql configuration requests")
        ipc_client.subscribe_to_topic(topic=config_req_topic, on_stream_event=on_event)

    def _get_config_response_json(self, config: ComponentConfiguration):
        container_name = config.get_container_name()
        port = config.get_host_port()
        db_name = DEFAULT_DB_NAME
        hostname = DEFAULT_HOST_NAME
        return {
            "hostname": hostname,
            "port": port,
            "container_name": container_name,
            "database": db_name,
        }
