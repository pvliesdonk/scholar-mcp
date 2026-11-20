#!/usr/bin/env bash
# Print the English Official Journal text of one EU act, by CELEX number.
#
# The Publications Office serves the text EUR-Lex shows, without EUR-Lex's
# bot challenge, when the request asks for XHTML in English. The quarterly
# CEN review (.github/workflows/cen-review.yml) lets its agent run this one
# command and no other shell, so the argument is checked before use and the
# only host it reaches is publications.europa.eu.
#
# Usage: scripts/fetch_oj.sh 32026D2479
set -euo pipefail

if [[ $# -ne 1 || ! "$1" =~ ^[0-9]{5}[A-Z]{1,2}[0-9]{4}(\([0-9]{2}\))?(-[0-9]{8})?$ ]]; then
  echo "usage: fetch_oj.sh CELEX, e.g. 32026D2479 or 02021D1182-20260617" >&2
  exit 2
fi

curl --silent --show-error --fail --location --max-time 60 \
  --proto '=https,http' --max-redirs 5 \
  --header 'Accept: application/xhtml+xml' \
  --header 'Accept-Language: eng' \
  "http://publications.europa.eu/resource/celex/$1" |
  sed -e 's/<[^>]*>/ /g' -e 's/&nbsp;/ /g' | tr -s ' \t' ' ' | grep -v '^ *$'
