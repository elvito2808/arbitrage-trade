"""Small Persian-language command line interface."""

from . import __version__


def main() -> None:
    while True:
        print("\n=== سامانه تحلیل آربیتراژ ===")
        print("1) نمایش وضعیت پروژه")
        print("2) نمایش محدودیت‌های ایمنی")
        print("0) خروج")
        choice = input("انتخاب شما: ").strip()
        if choice == "1":
            print(f"نسخه: {__version__}")
            print("حالت فعلی: فقط‌خواندنی؛ دریافت قیمت عمومی در حال توسعه است.")
        elif choice == "2":
            print("هیچ سفارش، معامله، امضا یا انتقال دارایی انجام نمی‌شود.")
            print("کلیدهای API و اطلاعات محرمانه را در مخزن یا گزارش‌ها قرار ندهید.")
        elif choice == "0":
            print("خروج.")
            return
        else:
            print("گزینه نامعتبر است؛ دوباره تلاش کنید.")


if __name__ == "__main__":
    main()
