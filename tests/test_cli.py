import json

from so101_wrapper.cli import main


def test_doctor_is_fake_only_and_reports_12d_contract(capsys):
    assert main(["doctor", "--backend", "fake", "--profile", "arms_only"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["backend"] == "fake"
    assert report["device_io"] is False
    assert report["action_dimension"] == 12
    assert report["sent_keys_match_schema"] is True
    assert report["lifecycle"] == "pass"


def test_doctor_reports_15d_mobile_profile(capsys):
    assert main(["doctor", "--profile", "arms_base"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["action_dimension"] == 15
