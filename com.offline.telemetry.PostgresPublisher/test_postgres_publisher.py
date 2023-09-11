import postgres_publisher as pub
import psycopg2.errors

point = {
    "TS": 0,
    "N": "name",
    "NS": "namespace",
    "U": "unit",
    "A": "aggregation",
    "V": "value",
    "thing_name": "thing_name",
}


def test_prepare_insert():
    table_name = "telemetry"

    sql = pub.prepare_insert(point, table_name)
    assert "INSERT INTO telemetry" in sql
    for k, v in point.items():
        assert str(k) in sql
        assert str(v) in sql


def test_send_telemetry(mocker):
    mock_conn = mocker.patch("psycopg2.connect")
    mock_DBConnection = mocker.Mock()
    mock_DBConnection.configure_mock(**{"get_conn.return_value": mock_conn})
    mock_cur = mock_conn.cursor.return_value

    pub.send_telemetry(mock_DBConnection, [point])
    mock_cur.execute.assert_called_once()
    mock_conn.commit.assert_called_once()
    mock_conn.rollback.assert_not_called()

    mock_conn.reset_mock()
    mock_cur.reset_mock()
    mock_cur.execute.side_effect = psycopg2.errors.InFailedSqlTransaction()

    pub.send_telemetry(mock_DBConnection, [point])
    mock_cur.execute.assert_called_once()
    mock_conn.commit.assert_not_called()
    mock_conn.rollback.assert_called_once()
