import pytest

from app.services.geofence_alerts import GeofenceAlertService
from app.schemas.alerts import AlertSeverity


@pytest.mark.parametrize(
    ("distance", "inside", "expected"),
    [
        (0.1, False, AlertSeverity.RED),
        (0.5, False, AlertSeverity.RED),
        (0.8, False, AlertSeverity.AMBER),
        (1.0, False, AlertSeverity.AMBER),
        (1.1, False, None),
        (10.0, True, AlertSeverity.RED),
    ],
)
def test_severity_thresholds(distance, inside, expected):
    assert GeofenceAlertService._severity(distance, inside) == expected
