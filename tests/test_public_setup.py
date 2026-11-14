"""Offline checks for public checkout discovery, pinning, and adapters."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('script',['sync_agent_tools.py','validate_agent_integrations.py'])
def test_agent_scripts_stay_with_their_own_checkout(tmp_path,monkeypatch,script):
    spec=importlib.util.spec_from_file_location('public_setup_'+script[:-3],ROOT/'scripts'/script)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    foreign=tmp_path/'other';(foreign/'.ai').mkdir(parents=True)
    (foreign/'.ai/manifest.json').write_text('{}')
    monkeypatch.setattr(module.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=0,stdout=str(foreign)))
    assert module.find_repo_root()==ROOT


def test_locked_install_failure_never_falls_back_to_unpinned_packages(tmp_path):
    venv=tmp_path/'venv';(venv/'bin').mkdir(parents=True)
    log=tmp_path/'calls.txt';python=venv/'bin/python'
    python.write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> "$MBG_TEST_CALLS"\ncase "$*" in *requirements-lock.txt*) exit 17 ;; esac\nexit 0\n')
    python.chmod(0o755)
    env={**os.environ,'MBG_VENV':str(venv),'MBG_PYTHON':str(python),'MBG_TEST_CALLS':str(log),'HOME':str(tmp_path/'home')}
    result=subprocess.run(['bash',str(ROOT/'install.sh'),'--stage','python'],env=env,capture_output=True,text=True)
    assert result.returncode!=0
    assert 'requirements.txt' not in log.read_text()


def test_public_manifest_rejects_an_unlisted_skill():
    spec=importlib.util.spec_from_file_location('public_manifest_sync',ROOT/'scripts/sync_agent_tools.py')
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    manifest={'release':{'canonical_skills':['mbg-agent-interface']},'capabilities':{}}
    with pytest.raises(module.SyncError):
        module.validate_manifest_refs(manifest,{'mbg-agent-interface':{},'unlisted-skill':{}})


def test_pdk_fetch_requires_an_explicit_revision_without_network(tmp_path):
    venv=tmp_path/'venv';(venv/'bin').mkdir(parents=True)
    log=tmp_path/'calls.txt';python=venv/'bin/python'
    python.write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> "$MBG_TEST_CALLS"\nexit 0\n');python.chmod(0o755)
    env={**os.environ,'MBG_VENV':str(venv),'MBG_PYTHON':str(python),'MBG_TEST_CALLS':str(log),'HOME':str(tmp_path/'home'),'PDK_ROOT':str(tmp_path/'pdk')}
    env.pop('MBG_PDK_VERSION',None)
    result=subprocess.run(['bash',str(ROOT/'install.sh'),'--stage','pdk'],env=env,capture_output=True,text=True)
    assert result.returncode!=0 and 'MBG_PDK_VERSION' in result.stdout+result.stderr
    assert not log.exists() or 'pip install' not in log.read_text()
