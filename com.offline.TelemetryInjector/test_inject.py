import inject
import pytest


class TestInjectState:
    @pytest.fixture
    def mock_component_states(self, mocker):
        return mocker.patch("health.get_all_components_states")

    def test_inject_state_adds_thing_name(self, mock_component_states):
        mock_component_states.return_value = [
            {"name": "a", "state": "RUNNING"},
            {"name": "b", "state": "BROKEN"},
        ]

        injected = inject.inject_state_to_telemetry([], "thing-name-0")
        for point in injected:
            assert point.get("thing_name") is not None

    def test_inject_state_adds_statuses(self, mock_component_states):
        mock_component_states.return_value = [
            {"name": "a", "state": "RUNNING"},
            {"name": "b", "state": "BROKEN"},
        ]

        injected = inject.inject_state_to_telemetry([], "thing-name-0")
        assert len(injected) == len(mock_component_states())
