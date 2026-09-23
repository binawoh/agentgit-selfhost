#!/bin/sh
set -eu
case "$(uname -s)" in
    Linux) ;;
    *) printf '%s\n' 'agit-selfhost requires Linux.' >&2; exit 1 ;;
esac
case "$(uname -m)" in
    x86_64|amd64) architecture=x64 ;;
    aarch64|arm64) architecture=arm64 ;;
    *) printf '%s\n' 'agit-selfhost supports Linux x64 and ARM64.' >&2; exit 1 ;;
esac
executable=$(readlink -f -- "$0")
directory=$(dirname -- "$executable")
exec "$directory/linux-$architecture/agit-selfhost" "$@"
