from argparse import ArgumentParser
import os


def main() -> None:
    parser = ArgumentParser(description="Generate a Kite Connect access token for the current day.")
    parser.add_argument("--api-key", default=os.environ.get("KITE_API_KEY"))
    parser.add_argument("--api-secret", default=os.environ.get("KITE_API_SECRET"))
    parser.add_argument("--request-token")
    args = parser.parse_args()

    if not args.api_key or not args.api_secret:
        raise SystemExit("Provide --api-key and --api-secret, or set KITE_API_KEY and KITE_API_SECRET.")

    try:
        from kiteconnect import KiteConnect
    except ImportError as exc:
        raise SystemExit("Install dependencies first: pip install -r requirements.txt") from exc

    kite = KiteConnect(api_key=args.api_key)
    if not args.request_token:
        print("Open this login URL, complete Kite login, then copy the request_token from the redirect URL:")
        print(kite.login_url())
        return

    data = kite.generate_session(args.request_token, api_secret=args.api_secret)
    print("Set this for today's session:")
    print(f"export KITE_ACCESS_TOKEN=\"{data['access_token']}\"")


if __name__ == "__main__":
    main()

