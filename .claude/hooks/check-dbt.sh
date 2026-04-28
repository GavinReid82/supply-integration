#!/usr/bin/env bash
project_root="/Users/gavin.reid/gavin/catalog_data_platform"
set -a
# shellcheck source=/dev/null
[ -f "$project_root/.env" ] && source "$project_root/.env"
set +a
cd "$project_root/dbt_project" || exit 1
output=$("$project_root/.venv/bin/dbt" parse 2>&1)
exit_code=$?
if [ $exit_code -ne 0 ]; then
  echo "$output" >&2
fi
exit $exit_code
