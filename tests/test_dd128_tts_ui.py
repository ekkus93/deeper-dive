from deeper_dive.hosts_screen import HostsScreen


def test_dd128_host_tts_actions_are_exposed() -> None:
    actions = (
        HostsScreen.action_discover_tts,
        HostsScreen.action_preview_voice,
        HostsScreen.action_install_kitten,
        HostsScreen.action_benchmark_tts,
    )
    assert all(callable(action) for action in actions)
