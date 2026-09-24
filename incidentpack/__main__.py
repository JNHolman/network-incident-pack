"""Allow `python -m incidentpack` to run the same supported CLI."""

from incidentpack.cli import main

raise SystemExit(main())
