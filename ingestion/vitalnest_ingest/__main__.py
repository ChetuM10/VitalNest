import sys

from vitalnest_ingest.cli import main
from vitalnest_ingest.env import load_env_files

load_env_files()  # reads ingestion/.env or ~/.vitalnest.env; a variable set in the shell still wins
sys.exit(main())
