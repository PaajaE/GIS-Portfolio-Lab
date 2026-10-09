"""The NIROPS listing crawler, exercised against a local fake directory tree (no network)."""

import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from firepath.probe import nirops_inventory

TREE = [
    "southwest/2022_Incidents/AZ-COF-000123_Tunnel/IR/20220419/20220419_2130_Tunnel_IR_HeatPerimeter.shp",
    "southwest/2022_Incidents/AZ-COF-000123_Tunnel/IR/20220420/20220420_2205_Tunnel_IR_HeatPerimeter.shp",
    "southwest/2022_Incidents/AZ-COF-000456_Double/IR/Pipeline/20220613_0115_Pipeline_IR.kmz",
    "southwest/2022_Incidents/AZ-COF-000456_Double/IR/Haywire/20220613_0120_Haywire_IR.kmz",
    "southwest/2021_Incidents/AZ-TNF-000777_Other/IR/20210605_IR.shp",
    "calif_n/2022_Incidents/CA-XXX_Mosquito/IR/x.shp",
]


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def test_crawler_finds_ir_files_and_timestamps(tmp_path):
    base = tmp_path / "public" / "incident_specific_data"
    for rel in TREE:
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Quiet, directory=str(tmp_path)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        root = f"http://127.0.0.1:{srv.server_address[1]}/public/incident_specific_data/"
        out = nirops_inventory(root=root, budget=100)
    finally:
        srv.shutdown()
    assert "southwest/" in out["regions"]
    tunnel = out["fires"]["Tunnel 2022"]
    assert sorted(f["timestamp_in_name"] for f in tunnel["ir_files"]) == ["20220419_2130", "20220420_2205"]
    pipe = {f["file"].rsplit("/", 1)[1] for f in out["fires"]["Pipeline 2022"]["ir_files"]}
    assert pipe == {"20220613_0115_Pipeline_IR.kmz", "20220613_0120_Haywire_IR.kmz"}
    assert "Telegraph 2021" not in out["fires"]
