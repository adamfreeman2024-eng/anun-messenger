#!/bin/sh
set -eu
python3 -m unittest spike.test_spike spike.test_phase3 spike.test_continue spike.test_product spike.test_reply spike.test_file_parts spike.test_disappear spike.test_opus spike.test_call_run spike.test_local spike.test_demo
