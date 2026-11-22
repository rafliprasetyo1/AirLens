"""QR alamat publik AirLens: cetak di terminal + simpan PNG (docs/assets/qr_expo.png). Dipakai `make expo-setup`.

    python -m airlens_trainer.qr <url> <png>
"""

import sys

import qrcode


def main() -> int:
    url, png = sys.argv[1], sys.argv[2]
    qr = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)
    qr.make_image(fill_color="black", back_color="white").save(png)
    print(f"QR {url} -> {png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
