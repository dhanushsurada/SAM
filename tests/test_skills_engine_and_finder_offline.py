"""
Unit tests for Skills Engine, Deterministic Finder Routing, and Skills API.
"""

import os
import sys
import tempfile
import atexit
import shutil
from pathlib import Path

# Set up isolated HOME
_test_home = tempfile.mkdtemp(prefix="sam_skills_test_")
os.environ["HOME"] = _test_home
atexit.register(lambda: shutil.rmtree(_test_home, ignore_errors=True))

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.skills_engine import SkillsEngine, parse_skill_md, DEFAULT_BUILTIN_SKILLS
from core.tiered_router import TieredExecutionRouter, ExecutionTier
from fastapi.testclient import TestClient
from interfaces.api.server import app

client = TestClient(app, client=("127.0.0.1", 12345))


def test_parse_skill_md():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "superpowers" / "skills" / "systematic-debugging"
        p.mkdir(parents=True)
        skill_file = p / "SKILL.md"
        skill_file.write_text(
            "---\n"
            "name: systematic-debugging\n"
            "description: 'Use when encountering any bug or test failure before proposing fixes'\n"
            "---\n"
            "# Systematic Debugging\n"
            "Find root cause first.\n",
            encoding="utf-8"
        )
        parsed = parse_skill_md(skill_file)
        assert parsed is not None
        assert parsed["name"] == "systematic-debugging"
        assert parsed["category"] == "superpowers"
        assert parsed["title"] == "Systematic Debugging"
        assert "systematic debugging" in parsed["triggers"]
        assert "Find root cause first." in parsed["content"]


def test_skills_engine_lifecycle():
    with tempfile.TemporaryDirectory() as td:
        skills_dir = Path(td) / "skills"
        plugins_dir = Path(td) / "plugins"
        p1 = plugins_dir / "anthropic-skills" / "skills" / "docx"
        p1.mkdir(parents=True)
        (p1 / "SKILL.md").write_text(
            "---\n"
            "name: docx\n"
            "description: 'Create and edit Word documents (.docx files)'\n"
            "---\n"
            "# Docx Skill\n",
            encoding="utf-8"
        )

        engine = SkillsEngine(data_dir=skills_dir, plugins_dir=plugins_dir)

        # 1. Scan and install
        scan_res = engine.scan_and_install_all_skills()
        assert scan_res["ok"] is True
        assert scan_res["total_installed"] == 1
        assert scan_res["by_category"].get("anthropic-agent") == 1

        # 2. List skills
        skills = engine.list_skills()
        assert len(skills) >= 1
        assert any(s["name"] == "docx" for s in skills)

        # 3. Create custom skill
        custom = engine.create_custom_skill(
            name="test-runner",
            title="Automated Test Runner",
            description="Runs pytest offline suite.",
            category="custom",
            triggers=["run tests", "pytest"],
            execution_type="system_command",
            command="echo 'Tests Passed'"
        )
        assert custom["name"] == "test-runner"
        assert custom["category"] == "custom"

        # 4. Execute custom skill
        exec_res = engine.execute_skill("test-runner")
        assert exec_res["ok"] is True
        assert "Tests Passed" in exec_res["stdout"]

        # 5. Toggle skill
        toggled = engine.toggle_skill("test-runner", False)
        assert toggled["enabled"] is False

        # Disabled skill execution fails gracefully
        exec_disabled = engine.execute_skill("test-runner")
        assert exec_disabled["ok"] is False

        # Re-enable
        engine.toggle_skill("test-runner", True)

        # 6. Delete custom skill
        del_res = engine.delete_custom_skill("test-runner")
        assert del_res is True
        assert not any(s["name"] == "test-runner" for s in engine.list_skills(category="custom"))


def test_deterministic_router_for_plugins_and_skills():
    router = TieredExecutionRouter()
    cmd = "open finder , open Plugins folder in Finder and install all the plugins and skills in the folder"
    res = router.route(cmd)
    assert res.tier == ExecutionTier.DIRECT
    assert res.action == "skills_scan_and_install"
    assert "successfully compiled and installed" in res.suggested_text


def test_api_skills_endpoints():
    # 1. GET /api/skills
    r_list = client.get("/api/skills")
    assert r_list.status_code == 200
    data = r_list.json()
    assert "skills" in data
    assert isinstance(data["skills"], list)

    # 2. POST /api/skills/custom
    r_create = client.post("/api/skills/custom", json={
        "name": "custom-echo",
        "title": "Custom Echo Service",
        "description": "Echoes back input payload",
        "category": "custom",
        "triggers": ["echo message", "repeat"],
        "execution_type": "system_command",
        "command": "echo 'Hello SAM'",
        "content": "Custom echo command"
    })
    assert r_create.status_code == 200
    created = r_create.json()["skill"]
    assert created["name"] == "custom-echo"

    # 3. POST /api/skills/{name}/execute
    r_exec = client.post("/api/skills/custom-echo/execute", json={"input": "World"})
    assert r_exec.status_code == 200
    exec_data = r_exec.json()
    assert exec_data["ok"] is True
    assert "Hello SAM" in exec_data["stdout"]

    # 4. POST /api/skills/{name}/toggle
    r_toggle = client.post("/api/skills/custom-echo/toggle", json={"enabled": False})
    assert r_toggle.status_code == 200
    assert r_toggle.json()["skill"]["enabled"] is False

    # 5. DELETE /api/skills/{name}
    r_del = client.delete("/api/skills/custom-echo")
    assert r_del.status_code == 200
    assert r_del.json()["ok"] is True
