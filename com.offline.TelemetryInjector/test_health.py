import health
import pytest

list_components_output = """
Component Name: aws.greengrass.telemetry.NucleusEmitter
    Version: 1.0.7
    State: RUNNING
    Configuration: {"mqttTopic":"","pubSubPublish":true,"telemetryPublishIntervalMs":10000.0}
    """


class TestHealth:
    @pytest.fixture
    def mock_list_components(self, mocker):
        return mocker.patch("health.list_components")

    def test_get_all_components_with_good_input(self, mock_list_components):
        should_match = {
            "name": "aws.greengrass.telemetry.NucleusEmitter",
            "version": "1.0.7",
            "state": "RUNNING",
            "configuration": {
                "mqttTopic": "",
                "pubSubPublish": True,
                "telemetryPublishIntervalMs": 10000.0,
            },
        }

        mock_list_components.return_value = list_components_output
        results = health.get_all_components()
        assert results[0] == should_match

    def test_get_all_components_with_bad_input(self, mock_list_components):
        mock_list_components.return_value = "bad input"
        with pytest.raises(ValueError):
            health.get_all_components()

    def test_get_all_components_states_with_good_input(self, mock_list_components):
        should_match = {
            "name": "aws.greengrass.telemetry.NucleusEmitter",
            "state": "RUNNING",
        }
        mock_list_components.return_value = list_components_output
        results = health.get_all_components_states()
        assert results[0] == should_match

    def test_get_all_components_states_with_bad_input(self, mock_list_components):
        mock_list_components.return_value = "bad input"
        with pytest.raises(ValueError):
            health.get_all_components_states()

    def test_error_bubbles(self, mock_list_components):
        mock_list_components.side_effect = ValueError()

        with pytest.raises(ValueError):
            health.get_all_components()
        with pytest.raises(ValueError):
            health.get_all_components_states()
