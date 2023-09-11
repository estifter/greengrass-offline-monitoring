import client
import pytest

from awsiot.greengrasscoreipc.model import (
    JsonMessage,
    BinaryMessage,
    MessageContext,
)


class TestConnectWithRetry:
    @pytest.fixture
    def mock_conn(self, mocker):
        return mocker.patch("client.remote_connection")

    @pytest.fixture
    def mock_sleep(self, mocker):
        mocker.patch("time.sleep")

    def test_retries_correct_number_of_times(self, mock_conn, mock_sleep):
        mock_conn.return_value = None

        with pytest.raises(ConnectionError):
            client.remote_connection_with_retry("end", 0, "", "", "", "", 10)
        assert mock_conn.call_count == 10

    def test_returns_without_retry_when_conn_made(self, mock_conn):
        mock_conn.return_value = "conn"

        assert (
            client.remote_connection_with_retry("end", 0, "", "", "", "", 10) == "conn"
        )
        mock_conn.assert_called_once()


class TestSafeGetMessageAndTopic:
    def test_binary_with_msg_and_with_ctxt(self):
        msg = client.SubscriptionResponseMessage(
            binary_message=BinaryMessage(
                message="hi", context=MessageContext(topic="t")
            )
        )
        assert client.safe_get_message_and_topic(msg) == (b"hi", "t")

    def test_binary_without_msg_and_with_ctxt(self):
        msg = client.SubscriptionResponseMessage(
            binary_message=BinaryMessage(
                message=None, context=MessageContext(topic="t")
            )
        )
        with pytest.raises(ValueError):
            client.safe_get_message_and_topic(msg)

    def test_binary_with_msg_and_without_ctxt(self):
        msg = client.SubscriptionResponseMessage(
            binary_message=BinaryMessage(message="hi", context=None)
        )
        with pytest.raises(ValueError):
            client.safe_get_message_and_topic(msg)

    def test_binary_without_msg_and_without_ctxt(self):
        msg = client.SubscriptionResponseMessage(
            binary_message=BinaryMessage(message=None, context=None)
        )
        with pytest.raises(ValueError):
            client.safe_get_message_and_topic(msg)

    def test_json_with_msg_and_with_ctxt(self):
        msg = client.SubscriptionResponseMessage(
            json_message=JsonMessage(
                message={"msg": "hi"}, context=MessageContext(topic="t")
            )
        )
        assert client.safe_get_message_and_topic(msg) == (b'{"msg": "hi"}', "t")

    def test_json_without_msg_and_with_ctxt(self):
        msg = client.SubscriptionResponseMessage(
            json_message=JsonMessage(message=None, context=MessageContext(topic="t"))
        )
        with pytest.raises(ValueError):
            client.safe_get_message_and_topic(msg)

    def test_json_with_msg_and_without_ctxt(self):
        msg = client.SubscriptionResponseMessage(
            json_message=JsonMessage(message={"msg": "hi"}, context=None)
        )
        with pytest.raises(ValueError):
            client.safe_get_message_and_topic(msg)

    def test_json_without_msg_and_without_ctxt(self):
        msg = client.SubscriptionResponseMessage(
            json_message=JsonMessage(message=None, context=None)
        )
        with pytest.raises(ValueError):
            client.safe_get_message_and_topic(msg)
