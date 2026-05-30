from app.imports.domain import ImportStatus


def test_import_status_active_values_are_worker_inputs():
    assert ImportStatus.active() == ("queued", "downloading", "ready_to_import")


def test_import_status_values_are_public_api_strings():
    assert ImportStatus.QUEUED.value == "queued"
    assert ImportStatus.DOWNLOADING.value == "downloading"
    assert ImportStatus.READY_TO_IMPORT.value == "ready_to_import"
    assert ImportStatus.IMPORTED.value == "imported"
    assert ImportStatus.FAILED.value == "failed"
    assert ImportStatus.CANCELED.value == "canceled"

