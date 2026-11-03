"""Persian numbered CLI for read-only market inspection."""

from . import __version__
from .adapters.kucoin import AdapterError, KuCoinAdapter


def _show_kucoin_quote() -> None:
    symbol = input("نماد بازار (مثلاً BTC-USDT): ").strip()
    try:
        quote = KuCoinAdapter().get_quote(symbol)
    except (AdapterError, ValueError) as exc:
        print(f"خطا در دریافت داده عمومی: {exc}")
        return
    print(f"بازار: {quote.symbol}")
    print(f"بهترین قیمت خرید (Bid): {quote.bid}")
    print(f"بهترین قیمت فروش (Ask): {quote.ask}")
    print(f"اختلاف قیمت: {quote.spread}")
    print(f"درصد اختلاف نسبت به Ask: {quote.spread_percent:.6f}%")
    print("منبع: KuCoin public market data")


def main() -> None:
    while True:
        print("\n=== سامانه تحلیل آربیتراژ ===")
        print("1) نمایش وضعیت پروژه")
        print("2) دریافت قیمت عمومی از KuCoin")
        print("3) نمایش محدودیت‌های ایمنی")
        print("0) خروج")
        choice = input("انتخاب شما: ").strip()
        if choice == "1":
            print(f"نسخه: {__version__}")
            print("حالت اجرا: فقط‌خواندنی")
            print("آداپتورهای اولیه: KuCoin Spot و PlunderSwap V2 (Zilliqa EVM)")
        elif choice == "2":
            _show_kucoin_quote()
        elif choice == "3":
            print("هیچ سفارش، معامله، امضا یا انتقال دارایی انجام نمی‌شود.")
            print("اتصال KuCoin عمومی است و به API key نیاز ندارد.")
            print("کلید خصوصی، عبارت بازیابی یا اطلاعات محرمانه را وارد یا ثبت نکنید.")
        elif choice == "0":
            print("خروج.")
            return
        else:
            print("گزینه نامعتبر است؛ دوباره تلاش کنید.")


if __name__ == "__main__":
    main()
