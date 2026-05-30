import json

from app.api.openapi_export import export_openapi, main


def test_export_openapi_writes_schema_with_mobile_client_contract(tmp_path):
    output = tmp_path / "openapi.json"

    exported = export_openapi(output)
    payload = json.loads(exported.read_text())

    assert exported == output
    assert payload["openapi"] == "3.1.0"
    assert "/sources/1337x/search" in payload["paths"]
    assert "/imports/1337x/{torrent_id}" in payload["paths"]
    assert "/downloads/{import_id}" in payload["paths"]
    assert "/tracks/{track_id}/stream" in payload["paths"]
    assert "Source1337xSearchResponse" in payload["components"]["schemas"]
    assert "DownloadStatusResponse" in payload["components"]["schemas"]
    assert "TrackListResponse" in payload["components"]["schemas"]


def test_export_openapi_cli_accepts_output_path(tmp_path):
    output = tmp_path / "schema" / "openapi.json"

    exit_code = main([str(output)])

    assert exit_code == 0
    assert output.is_file()

