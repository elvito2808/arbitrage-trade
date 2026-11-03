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
