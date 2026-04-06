import pytest

from atlas.config import AtlasConfig


def test_config_loads_baseline_and_deterministic_flags(tmp_path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
[system]
seed = 99
deterministic_mode = false
baseline_mode = "trident_no_rl"
twin_nodes = 3
governance_nodes = 3
episode_steps = 5
what_if_horizon = 2
max_candidates = 4
planner_mode = "mock"
""".strip(),
        encoding="utf-8",
    )

    config = AtlasConfig.from_toml(cfg_file)
    assert config.seed == 99
    assert config.deterministic_mode is False
    assert config.baseline_mode == "trident_no_rl"


def test_config_rejects_invalid_baseline_mode(tmp_path) -> None:
    cfg_file = tmp_path / "bad_config.toml"
    cfg_file.write_text(
        """
[system]
baseline_mode = "invalid_mode"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        AtlasConfig.from_toml(cfg_file)
