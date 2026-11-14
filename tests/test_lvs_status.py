"""LVS verdicts retain the report's success and failure evidence."""
import pytest
from mbg.checks import _parse_lvs_summary


@pytest.mark.parametrize('extra,expected', [('', True), ('Property errors were found.', False), ('Top level cell failed pin matching.', False)])
def test_report_status_agrees_with_match(tmp_path, extra, expected):
    report = tmp_path / 'cell.lvs.out'
    report.write_text('Final result: Circuits match uniquely.\n' + extra)
    result = _parse_lvs_summary(report)
    assert result['match'] is expected
    assert result['status'] == ('PASS' if expected else 'FAIL')


def test_absent_report_is_not_a_match(tmp_path):
    result = _parse_lvs_summary(tmp_path / 'absent.out')
    assert not result['match']
    assert result['status'] == 'ERROR'
