#!/bin/zsh
cd -- "${0:A:h}"
python3 connector/server.py --origin https://headroom-usage.vercel.app --open
