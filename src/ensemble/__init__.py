import sys
import argparse


def main() -> None:
    """
    Unified CLI entry point for the Ensemble Drama Engine.
    Routes subcommands:
      ensemble web                 Launch Web Studio & Live Player
      ensemble produce <file>      Produce entire book or chapter to audio
      ensemble cast <file>         Run AI Casting Producer
      ensemble <file> [options]    Direct/play audio drama
    """
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help", "help"):
        print("=" * 70)
        print("🎭 ENSEMBLE: Autonomous Multi-Cast Audio Drama Engine")
        print("=" * 70)
        print("Usage:")
        print("  ensemble web [--port PORT]             Launch Web Studio & Live Streaming Player")
        print("  ensemble produce <file> [--all]        Produce full book or chapter audio to disk")
        print("  ensemble cast <file>                   Run AI Casting Producer to build Cast Sheet")
        print("  ensemble <file> --all [--mp3]          Batch-produce all chapters in the book")
        print("  ensemble <file> --chapter X --play     Stream live audio drama to speakers")
        print("=" * 70)
        return

    subcmd = args[0]
    if subcmd == "web":
        sys.argv.pop(1)
        from ensemble.web.__main__ import main as web_main
        web_main()
    elif subcmd == "produce":
        sys.argv.pop(1)
        from ensemble.drama.__main__ import main as drama_main
        drama_main()
    elif subcmd == "cast":
        sys.argv.pop(1)
        from ensemble.producer.__main__ import main as producer_main
        producer_main()
    else:
        # Default directly to drama pipeline CLI (e.g. `ensemble samples/book.pdf --all`)
        from ensemble.drama.__main__ import main as drama_main
        drama_main()


if __name__ == "__main__":
    main()
