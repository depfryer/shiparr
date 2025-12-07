#!/bin/sh
set -e

# Note: We do not configure global git credentials here to avoid
# persisting sensitive tokens in the container's filesystem.
# Shiparr handles authentication securely at runtime.

# Execute the passed command
exec "$@"
