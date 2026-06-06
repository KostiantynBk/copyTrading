import tempfile
import unittest
from pathlib import Path

from copytrade_monitor.config import _discover_base_dir


class ConfigTests(unittest.TestCase):
    def test_discover_base_dir_prefers_project_root_over_unrelated_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            project_root = tmp_path / "copyTrading"
            module_path = project_root / "src" / "copytrade_monitor" / "config.py"
            unrelated_cwd = tmp_path / "elsewhere" / "runtime"

            (project_root / "src" / "copytrade_monitor").mkdir(parents=True)
            (project_root / "pyproject.toml").write_text("[project]\nname='x-copytrade-monitor'\n", encoding="utf-8")
            (project_root / ".env").write_text("OPENAI_API_KEY=test\n", encoding="utf-8")
            unrelated_cwd.mkdir(parents=True)

            base_dir = _discover_base_dir(unrelated_cwd, module_path)

            self.assertEqual(base_dir, project_root)


if __name__ == "__main__":
    unittest.main()
