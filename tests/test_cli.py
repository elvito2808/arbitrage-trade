from arbitrage_trade import cli


def test_status_menu_and_exit(monkeypatch, capsys):
    choices = iter(["1", "3", "0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(choices))

    cli.main()

    output = capsys.readouterr().out
    assert "نسخه:" in output
    assert "فقط‌خواندنی" in output
    assert "هیچ سفارش، معامله" in output
    assert "خروج." in output



def test_cli_configures_redacting_logging_on_entry(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "configure_logging", lambda: calls.append("configured"))
    choices = iter(["0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(choices))
    cli.main()
    assert calls == ["configured"]
