from markdown_deadlink_checker.models import ScanSummary

def test_scan_summary_has_errors():
    s = ScanSummary()
    assert s.has_errors is False
    s.errors.append("File read failed")
    assert s.has_errors is True
