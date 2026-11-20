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

# Cellar answers with redirects to http:// URLs on its own host. Follow them
# here, over HTTPS only, so nothing is fetched in clear text (#680) and no
# redirect can lead to another host.
body=$(mktemp)
trap 'rm -f "$body"' EXIT
url="https://publications.europa.eu/resource/celex/$1"
for _ in 1 2 3 4 5; do
  result=$(curl --silent --show-error --max-time 60 --proto '=https' \
    --header 'Accept: application/xhtml+xml' \
    --header 'Accept-Language: eng' \
    --output "$body" --write-out '%{http_code} %{redirect_url}' "$url")
  status=${result%% *}
  case "$status" in
    200)
      sed -e 's/<[^>]*>/ /g' -e 's/&nbsp;/ /g' "$body" | tr -s ' \t' ' ' | grep -v '^ *$'
      exit 0
      ;;
    30[1237])
      next=${result#* }
      if [[ ! "$next" =~ ^https?://publications\.europa\.eu/ ]]; then
        echo "fetch_oj.sh: refusing a redirect off publications.europa.eu" >&2
        exit 1
      fi
      url="https://${next#*://}"
      ;;
    *)
      echo "fetch_oj.sh: HTTP $status from $url" >&2
      exit 1
      ;;
  esac
done
echo "fetch_oj.sh: too many redirects" >&2
exit 1
