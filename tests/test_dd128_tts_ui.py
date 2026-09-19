from deeper_dive.hosts_screen import HostsScreen


def test_dd128_host_tts_actions_are_exposed() -> None:
    assert callable(HostsScreen.action_discover_tts)
    assert callable(HostsScreen.action_preview_voice)
    assert callable(HostsScreen.action_install_kitten)
    assert callable(HostsScreen.action_benchmark_tts)
